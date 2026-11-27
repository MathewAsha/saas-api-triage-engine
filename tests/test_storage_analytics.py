"""Unit tests for SQLite telemetry storage and SQL/Pandas analytics."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.analytics import export_telemetry_csvs, load_named_queries, run_telemetry_analytics
from src.har_parser import DEFAULT_SAMPLE_HAR, parse_har_file
from src.storage import get_connection, init_db, save_triage_session


class StorageAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = get_connection(":memory:")
        init_db(self.conn)
        records = parse_har_file(DEFAULT_SAMPLE_HAR)
        save_triage_session(self.conn, records, "sample_uat_session.har")

    def tearDown(self) -> None:
        self.conn.close()

    def test_load_named_queries_finds_all_four_telemetry_queries(self) -> None:
        queries = load_named_queries()
        self.assertEqual(
            set(queries.keys()),
            {
                "endpoint_error_and_latency_summary",
                "endpoint_p95_latency",
                "tenant_session_health",
                "slowest_requests_ranked",
            },
        )

    def test_run_telemetry_analytics_computes_p95_and_tenant_health(self) -> None:
        reports = run_telemetry_analytics(self.conn)

        p95_df = reports["endpoint_p95_latency"].set_index("endpoint_path")
        self.assertEqual(p95_df.loc["/api/v1/reports/export", "p95_latency_ms"], 3450.8)

        tenant_df = reports["tenant_session_health"].set_index("tenant")
        self.assertEqual(tenant_df.loc["acme_corp", "auth_errors"], 1)
        self.assertEqual(tenant_df.loc["acme_corp", "rate_limits"], 1)
        self.assertEqual(tenant_df.loc["globex", "server_errors"], 1)
        self.assertEqual(tenant_df.loc["globex", "high_latency_calls"], 1)

    def test_export_telemetry_csvs_creates_four_files(self) -> None:
        reports = run_telemetry_analytics(self.conn)
        with tempfile.TemporaryDirectory() as tmp_dir:
            written = export_telemetry_csvs(reports, output_dir=tmp_dir)
            self.assertEqual(len(written), 4)
            for path in written:
                self.assertTrue(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
