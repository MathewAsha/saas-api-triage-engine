"""SQLite telemetry warehouse for storing sanitized HAR triage sessions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.har_parser import DEFAULT_SAMPLE_HAR, parse_har_file

DEFAULT_DB_PATH = Path("data/telemetry.db")


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create normalized telemetry tables if they do not exist."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                total_requests INTEGER NOT NULL,
                flagged_requests INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                started_at TEXT,
                method TEXT NOT NULL,
                endpoint_path TEXT NOT NULL,
                tenant TEXT NOT NULL,
                status INTEGER NOT NULL,
                time_ms REAL NOT NULL,
                issue_category TEXT NOT NULL,
                needs_triage INTEGER NOT NULL,
                trace_id TEXT,
                root_cause_hint TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES triage_sessions (session_id)
                    ON DELETE CASCADE
            );
            """
        )


def save_triage_session(
    conn: sqlite3.Connection,
    records: list[dict[str, Any]],
    source_file: str,
) -> int:
    """Persist one HAR capture session and its parsed API request rows."""
    uploaded_at = datetime.now(timezone.utc).isoformat()
    flagged_count = sum(1 for item in records if item.get("needs_triage"))

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO triage_sessions (source_file, uploaded_at, total_requests, flagged_requests)
            VALUES (?, ?, ?, ?);
            """,
            (source_file, uploaded_at, len(records), flagged_count),
        )
        session_id = int(cursor.lastrowid)

        rows = [
            (
                session_id,
                item.get("started_at"),
                item["method"],
                item["endpoint_path"],
                item["tenant"],
                int(item["status"]),
                float(item["time_ms"]),
                item["issue_category"],
                int(bool(item["needs_triage"])),
                item.get("trace_id"),
                item["root_cause_hint"],
            )
            for item in records
        ]
        conn.executemany(
            """
            INSERT INTO api_requests (
                session_id, started_at, method, endpoint_path, tenant,
                status, time_ms, issue_category, needs_triage, trace_id, root_cause_hint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows,
        )
    return session_id


def main() -> None:
    """Parse the sample HAR capture and store it in data/telemetry.db."""
    records = parse_har_file(DEFAULT_SAMPLE_HAR)
    conn = get_connection()
    try:
        init_db(conn)
        session_id = save_triage_session(conn, records, DEFAULT_SAMPLE_HAR.name)
        total_rows = conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
    finally:
        conn.close()

    print(f"Saved session #{session_id} ({len(records)} requests) -> {DEFAULT_DB_PATH}")
    print(f"Total API request telemetry rows in DB: {total_rows}")


if __name__ == "__main__":
    main()
