"""Unit tests for HAR parsing, secret redaction, and root-cause classification."""

from __future__ import annotations

import unittest

from src.har_parser import (
    DEFAULT_SAMPLE_HAR,
    classify_entry,
    parse_har_file,
    redact_headers,
    summarize_triage,
)


class HarParserTests(unittest.TestCase):
    def test_redact_headers_masks_bearer_cookies_and_api_keys(self) -> None:
        raw_headers = [
            {"name": "Authorization", "value": "Bearer super-secret-jwt"},
            {"name": "Cookie", "value": "session_id=xyz987"},
            {"name": "x-api-key", "value": "key-123"},
            {"name": "Accept", "value": "application/json"},
        ]
        cleaned = redact_headers(raw_headers)
        self.assertEqual(cleaned["Authorization"], "Bearer ***REDACTED***")
        self.assertEqual(cleaned["Cookie"], "***REDACTED***")
        self.assertEqual(cleaned["x-api-key"], "***REDACTED***")
        self.assertEqual(cleaned["Accept"], "application/json")

    def test_classify_entry_identifies_support_categories(self) -> None:
        self.assertEqual(classify_entry(401, 100.0)[0], "AUTH_ERROR")
        self.assertEqual(classify_entry(429, 90.0)[0], "RATE_LIMIT")
        self.assertEqual(classify_entry(502, 500.0)[0], "SERVER_ERROR")
        self.assertEqual(classify_entry(200, 3200.0, slow_threshold_ms=2000.0)[0], "HIGH_LATENCY")
        self.assertEqual(classify_entry(200, 120.0, slow_threshold_ms=2000.0)[0], "HEALTHY")

    def test_parse_har_file_reads_sample_and_redacts_secrets(self) -> None:
        records = parse_har_file(DEFAULT_SAMPLE_HAR)
        self.assertEqual(len(records), 5)

        auth_entry = next(r for r in records if r["status"] == 401)
        self.assertEqual(auth_entry["tenant"], "acme_corp")
        self.assertEqual(auth_entry["request_headers"]["Authorization"], "Bearer ***REDACTED***")
        self.assertEqual(auth_entry["request_headers"]["Cookie"], "***REDACTED***")
        self.assertTrue(auth_entry["needs_triage"])

    def test_summarize_triage_counts_flagged_and_slowest(self) -> None:
        records = parse_har_file(DEFAULT_SAMPLE_HAR)
        summary = summarize_triage(records)
        self.assertEqual(summary["total_requests"], 5)
        self.assertEqual(summary["healthy_count"], 1)
        self.assertEqual(summary["needs_triage_count"], 4)
        self.assertEqual(summary["slowest_endpoint"], "/api/v1/reports/export")


if __name__ == "__main__":
    unittest.main()
