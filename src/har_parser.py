"""Chrome DevTools HAR parser, secret redactor, and root-cause classifier.

Helps Technical & Product Support Engineers turn raw HAR network captures
into sanitized, diagnostic-ready incident records without leaking credentials.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SECRET_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
}
DEFAULT_SAMPLE_HAR = Path("samples/sample_uat_session.har")
DEFAULT_SLOW_THRESHOLD_MS = 2000.0


def redact_headers(headers: list[dict[str, Any]] | None) -> dict[str, str]:
    """Convert HAR header list to a dict while masking sensitive auth/cookie values."""
    cleaned: dict[str, str] = {}
    for item in headers or []:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        value = str(item.get("value", ""))
        if name.lower() in SECRET_HEADER_NAMES:
            if name.lower() == "authorization" and value.lower().startswith("bearer "):
                cleaned[name] = "Bearer ***REDACTED***"
            else:
                cleaned[name] = "***REDACTED***"
        else:
            cleaned[name] = value
    return cleaned


def classify_entry(
    status: int,
    time_ms: float,
    slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
) -> tuple[str, str]:
    """Classify an HTTP call into a support triage category and root-cause hint."""
    if status in (401, 403):
        return (
            "AUTH_ERROR",
            "Authentication or permission failure (check expired Bearer token, API key, or role scope).",
        )
    if status == 429:
        return (
            "RATE_LIMIT",
            "API rate limit exceeded (inspect Retry-After header or client burst frequency).",
        )
    if 400 <= status < 500:
        return (
            "CLIENT_ERROR",
            "Client request error (verify endpoint path, query parameters, or JSON body).",
        )
    if status >= 500 or status == 0:
        return (
            "SERVER_ERROR",
            "Backend or upstream connector failure (escalate to engineering with trace ID and payload).",
        )
    if time_ms > slow_threshold_ms:
        return (
            "HIGH_LATENCY",
            f"Slow response exceeding {slow_threshold_ms:.0f}ms threshold (check DB query or downstream timeout).",
        )
    return ("HEALTHY", "Request completed normally within latency threshold.")


def parse_har_file(
    har_path: str | Path,
    slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS,
) -> list[dict[str, Any]]:
    """Parse a Chrome DevTools .har JSON file into sanitized triage records."""
    raw_data = json.loads(Path(har_path).read_text(encoding="utf-8"))
    entries = raw_data.get("log", {}).get("entries", [])

    records: list[dict[str, Any]] = []
    for entry in entries:
        request = entry.get("request", {})
        response = entry.get("response", {})

        url = str(request.get("url", ""))
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        tenant = query_params.get("tenant", ["default"])[0]

        status = int(response.get("status", 0))
        time_ms = round(float(entry.get("time", 0.0)), 2)
        category, hint = classify_entry(status, time_ms, slow_threshold_ms)

        content_text = str(response.get("content", {}).get("text", "")).strip()
        response_headers = {
            str(h.get("name", "")): str(h.get("value", ""))
            for h in response.get("headers", [])
            if h.get("name")
        }

        records.append(
            {
                "started_at": entry.get("startedDateTime"),
                "method": str(request.get("method", "GET")).upper(),
                "url": url,
                "endpoint_path": parsed_url.path or "/",
                "tenant": tenant,
                "status": status,
                "time_ms": time_ms,
                "issue_category": category,
                "needs_triage": category != "HEALTHY",
                "root_cause_hint": hint,
                "trace_id": response_headers.get("X-Trace-Id"),
                "request_headers": redact_headers(request.get("headers")),
                "response_snippet": content_text[:200],
            }
        )
    return records


def summarize_triage(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute high-level counts and slowest request from parsed HAR records."""
    counts = Counter(item["issue_category"] for item in records)
    triage_items = [item for item in records if item["needs_triage"]]
    slowest = max(records, key=lambda item: item["time_ms"], default=None)
    return {
        "total_requests": len(records),
        "needs_triage_count": len(triage_items),
        "healthy_count": counts.get("HEALTHY", 0),
        "category_breakdown": dict(counts),
        "slowest_endpoint": slowest["endpoint_path"] if slowest else None,
        "slowest_time_ms": slowest["time_ms"] if slowest else 0.0,
    }


def main() -> None:
    """Run Step 1 HAR triage against the synthetic UAT sample capture."""
    records = parse_har_file(DEFAULT_SAMPLE_HAR)
    summary = summarize_triage(records)

    print(f"Analyzed {summary['total_requests']} requests from {DEFAULT_SAMPLE_HAR}")
    print(
        f"Healthy: {summary['healthy_count']} | "
        f"Needs triage: {summary['needs_triage_count']} | "
        f"Breakdown: {summary['category_breakdown']}"
    )
    print("\nFlagged Issues (secrets automatically redacted):")
    for item in records:
        if not item["needs_triage"]:
            continue
        print(
            f"  [{item['issue_category']}] {item['method']} {item['endpoint_path']} "
            f"(tenant={item['tenant']}, status={item['status']}, time={item['time_ms']}ms)"
        )
        print(f"     Hint: {item['root_cause_hint']}")
        print(f"     Headers: {item['request_headers']}")


if __name__ == "__main__":
    main()
