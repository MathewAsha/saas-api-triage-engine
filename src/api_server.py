"""FastAPI microservice with live Swagger UI (/docs) for HAR triage & telemetry."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from src.analytics import run_telemetry_analytics
from src.bug_report import generate_ado_bug_markdown
from src.har_parser import (
    DEFAULT_SAMPLE_HAR,
    DEFAULT_SLOW_THRESHOLD_MS,
    parse_har_file,
    summarize_triage,
)
from src.storage import DEFAULT_DB_PATH, get_connection, init_db, save_triage_session

app = FastAPI(
    title="SaaS API & HAR Log Triage Engine",
    version="1.0.0",
    description=(
        "Upload Chrome DevTools .har captures to automatically redact secrets, "
        "classify HTTP/latency root causes, generate Azure DevOps bug tickets, "
        "and query SQL telemetry (p95 latency & tenant health)."
    ),
)

DB_PATH_OVERRIDE: Path | None = None


def _active_db_path() -> Path:
    return DB_PATH_OVERRIDE if DB_PATH_OVERRIDE is not None else DEFAULT_DB_PATH


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Verify the triage API service is running."""
    return {"status": "ok", "service": "saas-api-triage-engine"}


@app.post("/triage/har", tags=["Triage"])
async def triage_har_upload(
    file: UploadFile = File(..., description="Chrome DevTools .har JSON file"),
    slow_threshold_ms: float = Query(
        DEFAULT_SLOW_THRESHOLD_MS,
        ge=100.0,
        description="Latency threshold in ms above which 2xx calls are flagged",
    ),
) -> dict[str, Any]:
    """Parse an uploaded .har file, mask secrets, store telemetry, and return ADO markdown."""
    raw_bytes = await file.read()
    try:
        json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid HAR JSON file: {exc}") from exc

    with tempfile.NamedTemporaryFile(suffix=".har", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = Path(tmp.name)

    try:
        records = parse_har_file(tmp_path, slow_threshold_ms=slow_threshold_ms)
    finally:
        tmp_path.unlink(missing_ok=True)

    source_name = file.filename or "uploaded_capture.har"
    conn = get_connection(_active_db_path())
    try:
        init_db(conn)
        session_id = save_triage_session(conn, records, source_file=source_name)
    finally:
        conn.close()

    return {
        "session_id": session_id,
        "source_file": source_name,
        "summary": summarize_triage(records),
        "flagged_entries": [r for r in records if r["needs_triage"]],
        "ado_bug_markdown": generate_ado_bug_markdown(records, source_name=source_name),
    }


@app.get("/analytics/summary", tags=["Analytics"])
def get_analytics_summary() -> dict[str, Any]:
    """Run SQL analytics (p95 latency, error rates, tenant health) from SQLite."""
    conn = get_connection(_active_db_path())
    try:
        init_db(conn)
        reports = run_telemetry_analytics(conn)
    finally:
        conn.close()

    return {
        name: df.to_dict(orient="records")
        for name, df in reports.items()
    }


@app.get("/uat-simulator/sample-har", tags=["UAT Simulator"])
def get_sample_uat_har() -> dict[str, Any]:
    """Return a synthetic UAT .har payload so users can test without company data."""
    if not DEFAULT_SAMPLE_HAR.exists():
        raise HTTPException(status_code=404, detail="Sample HAR fixture not found")
    return json.loads(DEFAULT_SAMPLE_HAR.read_text(encoding="utf-8"))
