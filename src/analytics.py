"""Pandas telemetry analytics runner powered by sql/triage_queries.sql."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.storage import DEFAULT_DB_PATH, get_connection

DEFAULT_SQL_PATH = Path("sql/triage_queries.sql")
DEFAULT_REPORTS_DIR = Path("reports")


def load_named_queries(sql_path: str | Path = DEFAULT_SQL_PATH) -> dict[str, str]:
    """Parse `-- name: <query_name>` blocks from a .sql file."""
    text = Path(sql_path).read_text(encoding="utf-8")
    queries: dict[str, str] = {}
    current_name: str | None = None
    buffer: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("-- name:"):
            if current_name and buffer:
                queries[current_name] = "\n".join(buffer).strip()
            current_name = stripped.split(":", 1)[1].strip()
            buffer = []
        elif current_name is not None:
            buffer.append(line)

    if current_name and buffer:
        queries[current_name] = "\n".join(buffer).strip()

    return queries


def run_telemetry_analytics(
    conn: sqlite3.Connection,
    sql_path: str | Path = DEFAULT_SQL_PATH,
) -> dict[str, pd.DataFrame]:
    """Run all telemetry SQL queries and return DataFrames keyed by query name."""
    queries = load_named_queries(sql_path)
    return {
        name: pd.read_sql_query(sql, conn)
        for name, sql in queries.items()
    }


def export_telemetry_csvs(
    reports: dict[str, pd.DataFrame],
    output_dir: str | Path = DEFAULT_REPORTS_DIR,
) -> list[Path]:
    """Export each analytics DataFrame to CSV inside output_dir."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, df in reports.items():
        path = out_path / f"{name}.csv"
        df.to_csv(path, index=False)
        written.append(path)
    return written


def main() -> None:
    """Run all SQL telemetry reports against data/telemetry.db and print/export them."""
    if not DEFAULT_DB_PATH.exists():
        raise SystemExit(
            f"Database not found at {DEFAULT_DB_PATH}. Run `python -m src.storage` first."
        )

    conn = get_connection(DEFAULT_DB_PATH)
    try:
        reports = run_telemetry_analytics(conn)
    finally:
        conn.close()

    csv_files = export_telemetry_csvs(reports)

    print("=== 1. Endpoint Error Rate & Latency Summary ===")
    print(reports["endpoint_error_and_latency_summary"].to_string(index=False))

    print("\n=== 2. Endpoint p95 Latency (CTE + Window Function) ===")
    print(reports["endpoint_p95_latency"].to_string(index=False))

    print("\n=== 3. Tenant Session Health (JOIN) ===")
    print(reports["tenant_session_health"].to_string(index=False))

    print("\n=== 4. Slowest Requests Ranked Per Tenant (Window Function) ===")
    print(reports["slowest_requests_ranked"].to_string(index=False))

    print("\nExported telemetry CSVs:")
    for path in csv_files:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
