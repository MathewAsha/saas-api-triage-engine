"""Unit tests for sanitized cURL and ADO Markdown bug report generation."""

from __future__ import annotations

import unittest

from src.bug_report import build_safe_curl, generate_ado_bug_markdown
from src.har_parser import DEFAULT_SAMPLE_HAR, parse_har_file


class BugReportTests(unittest.TestCase):
    def test_build_safe_curl_uses_only_redacted_headers(self) -> None:
        entry = {
            "method": "GET",
            "url": "https://uat.example.com/api/v1/tickets",
            "request_headers": {
                "Authorization": "Bearer ***REDACTED***",
                "Accept": "application/json",
            },
        }
        cmd = build_safe_curl(entry)
        self.assertIn("Bearer ***REDACTED***", cmd)
        self.assertIn("curl -X GET", cmd)

    def test_generate_ado_bug_markdown_includes_summary_table_and_redaction(self) -> None:
        records = parse_har_file(DEFAULT_SAMPLE_HAR)
        md = generate_ado_bug_markdown(records, source_name="sample_uat_session.har")
        self.assertIn("Flagged Incidents Summary", md)
        self.assertIn("`AUTH_ERROR`", md)
        self.assertIn("`dd-trace-778899`", md)
        self.assertNotIn("fake-expired-jwt-token-999", md)
        self.assertNotIn("abc123secretcookie", md)


if __name__ == "__main__":
    unittest.main()
