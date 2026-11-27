-- Datadog-style SQL telemetry queries for SaaS API & HAR Triage Engine
-- Compatible with SQLite 3.25+ and PostgreSQL.

-- name: endpoint_error_and_latency_summary
-- 1. Aggregation + CASE: Compute request count, error rate %, avg latency, and max latency per endpoint.
SELECT
    endpoint_path,
    method,
    COUNT(*) AS total_calls,
    SUM(CASE WHEN status >= 400 OR status = 0 THEN 1 ELSE 0 END) AS error_calls,
    ROUND(
        100.0 * SUM(CASE WHEN status >= 400 OR status = 0 THEN 1 ELSE 0 END) / COUNT(*),
        1
    ) AS error_rate_pct,
    ROUND(AVG(time_ms), 2) AS avg_latency_ms,
    ROUND(MAX(time_ms), 2) AS max_latency_ms
FROM api_requests
GROUP BY endpoint_path, method
ORDER BY error_rate_pct DESC, max_latency_ms DESC;

-- name: endpoint_p95_latency
-- 2. CTE + Window Functions: Calculate exact 95th percentile (p95) latency per endpoint.
WITH ranked_latencies AS (
    SELECT
        endpoint_path,
        time_ms,
        ROW_NUMBER() OVER (PARTITION BY endpoint_path ORDER BY time_ms ASC) AS rn,
        COUNT(*) OVER (PARTITION BY endpoint_path) AS total_cnt
    FROM api_requests
)
SELECT
    endpoint_path,
    total_cnt AS sample_size,
    ROUND(time_ms, 2) AS p95_latency_ms
FROM ranked_latencies
WHERE rn = ((total_cnt * 95 + 99) / 100)
ORDER BY p95_latency_ms DESC;

-- name: tenant_session_health
-- 3. JOIN + Aggregation: Summarize triage issues by customer tenant and capture session.
SELECT
    r.tenant,
    s.source_file,
    COUNT(r.request_id) AS total_calls,
    SUM(r.needs_triage) AS flagged_calls,
    SUM(CASE WHEN r.issue_category = 'AUTH_ERROR' THEN 1 ELSE 0 END) AS auth_errors,
    SUM(CASE WHEN r.issue_category = 'RATE_LIMIT' THEN 1 ELSE 0 END) AS rate_limits,
    SUM(CASE WHEN r.issue_category = 'SERVER_ERROR' THEN 1 ELSE 0 END) AS server_errors,
    SUM(CASE WHEN r.issue_category = 'HIGH_LATENCY' THEN 1 ELSE 0 END) AS high_latency_calls
FROM api_requests AS r
INNER JOIN triage_sessions AS s
    ON r.session_id = s.session_id
GROUP BY r.tenant, s.source_file
ORDER BY flagged_calls DESC, r.tenant ASC;

-- name: slowest_requests_ranked
-- 4. Window Functions: Rank slowest calls per tenant alongside each tenant's average latency.
SELECT
    tenant,
    method,
    endpoint_path,
    status,
    issue_category,
    time_ms,
    ROUND(AVG(time_ms) OVER (PARTITION BY tenant), 2) AS tenant_avg_ms,
    DENSE_RANK() OVER (PARTITION BY tenant ORDER BY time_ms DESC) AS slow_rank_in_tenant
FROM api_requests
ORDER BY tenant ASC, slow_rank_in_tenant ASC;
