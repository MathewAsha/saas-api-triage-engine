"""Generate Azure DevOps / Jira-ready Markdown bug reports from parsed HAR data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.har_parser import DEFAULT_SAMPLE_HAR, parse_har_file, summarize_triage


def build_safe_curl(entry: dict[str, Any]) -> str:
    """Build a reproduction curl command using only redacted request headers."""
    lines = [f"curl -X {entry['method']} \"{entry['url']}\""]
    for name, value in entry.get("request_headers", {}).items():
        lines.append(f'  -H "{name}: {value}"')
    return " \\\n".join(lines)


def generate_ado_bug_markdown(
    records: list[dict[str, Any]],
    source_name: str = "sample_uat_session.har",
) -> str:
    """Format flagged HAR incidents into a sanitized Markdown bug report."""
    summary = summarize_triage(records)
    flagged = [r for r in records if r["needs_triage"]]

    lines = [
        f"## API Triage & Root-Cause Report (`{source_name}`)",
        "",
        f"- **Total Requests Analyzed:** {summary['total_requests']}",
        f"- **Healthy:** {summary['healthy_count']} | **Flagged for Triage:** {summary['needs_triage_count']}",
        f"- **Slowest Endpoint:** `{summary['slowest_endpoint']}` ({summary['slowest_time_ms']} ms)",
        "",
    ]

    if not flagged:
        lines.append("No errors or high-latency calls detected in this capture.")
        return "\n".join(lines)

    lines.extend(
        [
            "### Flagged Incidents Summary",
            "| Category | Method | Endpoint | Tenant | Status | Latency (ms) | Trace ID |",
            "|---|---|---|---|---:|---:|---|",
        ]
    )
    for item in flagged:
        trace_id = item.get("trace_id") or "N/A"
        lines.append(
            f"| `{item['issue_category']}` | {item['method']} | `{item['endpoint_path']}` "
            f"| `{item['tenant']}` | {item['status']} | {item['time_ms']} | `{trace_id}` |"
        )

    lines.extend(["", "### Detailed Diagnostics & Sanitized Reproduction Steps"])
    for idx, item in enumerate(flagged, start=1):
        lines.extend(
            [
                f"#### {idx}. [{item['issue_category']}] {item['method']} `{item['endpoint_path']}` (HTTP {item['status']})",
                f"- **Root-Cause Hint:** {item['root_cause_hint']}",
                f"- **Response Snippet:** `{item['response_snippet'] or 'N/A'}`",
                "- **Sanitized cURL:**",
                "```bash",
                build_safe_curl(item),
                "```",
                "",
            ]
        )

    return "\n".join(lines).strip()


def main() -> None:
    """Parse the sample HAR and write/print an ADO-ready Markdown bug report."""
    records = parse_har_file(DEFAULT_SAMPLE_HAR)
    markdown = generate_ado_bug_markdown(records, source_name=DEFAULT_SAMPLE_HAR.name)

    out_path = Path("reports/latest_bug_report.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"\nSaved Markdown report -> {out_path}")


if __name__ == "__main__":
    main()
