"""API integration tests for the FastAPI HAR triage server."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import src.api_server as api_server
from src.har_parser import DEFAULT_SAMPLE_HAR


class ApiServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_db = api_server.DB_PATH_OVERRIDE
        api_server.DB_PATH_OVERRIDE = Path(self.tmp_dir.name) / "api_test.db"
        self.client = TestClient(api_server.app)

    def tearDown(self) -> None:
        api_server.DB_PATH_OVERRIDE = self.orig_db
        self.tmp_dir.cleanup()

    def test_health_endpoint_returns_ok(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_triage_har_upload_stores_session_and_exposes_analytics(self) -> None:
        har_bytes = DEFAULT_SAMPLE_HAR.read_bytes()
        resp = self.client.post(
            "/triage/har",
            files={"file": ("sample_uat_session.har", har_bytes, "application/json")},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["summary"]["total_requests"], 5)
        self.assertEqual(body["summary"]["needs_triage_count"], 4)
        self.assertNotIn("fake-expired-jwt-token-999", body["ado_bug_markdown"])

        analytics_resp = self.client.get("/analytics/summary")
        self.assertEqual(analytics_resp.status_code, 200)
        analytics = analytics_resp.json()
        self.assertGreaterEqual(len(analytics["endpoint_p95_latency"]), 1)

    def test_triage_har_rejects_invalid_json_with_400(self) -> None:
        resp = self.client.post(
            "/triage/har",
            files={"file": ("broken.har", b"{not valid json", "application/json")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_uat_simulator_returns_sample_har(self) -> None:
        resp = self.client.get("/uat-simulator/sample-har")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("log", resp.json())


if __name__ == "__main__":
    unittest.main()
