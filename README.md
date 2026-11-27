# SaaS API & HAR Log Triage Engine

![Unit Tests](https://github.com/MathewAsha/saas-api-triage-engine/actions/workflows/tests.yml/badge.svg)

A production-style **Product Support & API Implementation** tool that parses Chrome DevTools `.har` network captures, automatically redacts sensitive credentials (`Authorization`, `Cookie`, `x-api-key`), classifies HTTP/latency root causes, generates ready-to-paste **Azure DevOps / Jira** bug tickets, persists request telemetry to SQLite, runs **p95 latency & tenant error analytics** (SQL + Pandas), and exposes a live **FastAPI + Swagger UI (`/docs`)** service.

## Tech Stack
- **Support & API Integration:** Python, FastAPI, Swagger/OpenAPI (`/docs`), Chrome DevTools HAR Parsing, Secret Redaction, Sanitized `curl` Generation, Postman Collection
- **Telemetry & Data Analytics:** SQLite, SQL (JOINs, CTEs, Window Functions, p95 Latency, `CASE` aggregations), Pandas, CSV Export
- **Testing & CI:** `unittest`, FastAPI `TestClient`, GitHub Actions CI

## Project Structure
```text
saas-api-triage-engine/
├── .github/workflows/
│   └── tests.yml
├── postman/
│   └── saas-api-triage-engine.postman_collection.json
├── samples/
│   └── sample_uat_session.har   # Safe synthetic UAT capture (no real data)
├── sql/
│   └── triage_queries.sql
├── src/
│   ├── har_parser.py            # HAR parsing, header secret redaction & root-cause tags
│   ├── bug_report.py            # ADO/Jira Markdown bug generator with safe curl
│   ├── storage.py               # SQLite telemetry warehouse (triage_sessions + api_requests)
│   ├── analytics.py             # Pandas SQL runner & CSV exporter
│   └── api_server.py            # FastAPI service + live Swagger UI (/docs)
├── tests/
│   ├── test_har_parser.py
│   ├── test_bug_report.py
│   ├── test_storage_analytics.py
│   └── test_api_server.py
├── requirements.txt
└── README.md
```

## Quick Start
```powershell
pip install -r requirements.txt

# 1. Run all unit & API tests
python -m unittest discover -s tests -v

# 2. Parse the synthetic UAT capture & generate an ADO-ready bug report
python -m src.har_parser
python -m src.bug_report

# 3. Store telemetry in SQLite & run p95 latency / tenant SQL analytics
python -m src.storage
python -m src.analytics

# 4. Launch the FastAPI + Swagger UI server (open http://127.0.0.1:8000/docs)
uvicorn src.api_server:app --reload
```
