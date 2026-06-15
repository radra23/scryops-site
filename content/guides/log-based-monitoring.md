---
title: "Log-Based Monitoring"
date: 2026-06-10
draft: true
excerpt: "Logs carry operational state at a resolution metrics can't match. Most teams archive them. This guide covers how to query them continuously and alert on what they surface."
readtime: 10
tags: ["Logs", "Observability", "Alerting", "Structured Logging"]
---

A metric tells you a rate changed. A log tells you which request failed, on which endpoint, for which user, with which error code, after which dependency returned a 503. Metrics are the summary; logs are the evidence. Log-based monitoring is the practice of treating that evidence stream as a continuous operational signal — not an archive you open after something goes wrong.

## What Log-Based Monitoring Is (and Isn't)

Most teams use logs in one mode: reactive forensics. An alert fires, someone opens the log browser, and they start searching. Logs are the autopsy tool. That is a valid use. It is not monitoring.

Active monitoring means persistent queries running continuously against your log stream, thresholds configured, and alerts wired to fire when conditions are met. The difference between mode one and mode two is not the tool — you can do both in Grafana, Kibana, or CloudWatch. The difference is whether those queries exist as long-lived rules or only as one-off searches you run manually.

Log-based monitoring requires exactly three things, the same three things metric-based monitoring requires: a structured data source, a query layer, and an alerting rule. Swap time-series data for event streams and the architecture is identical. What makes it harder in practice is that logs arrive at the query layer in a form that resists aggregation — unstructured text, inconsistent field names, and missing fields — unless you enforce structure at the source.

A useful test: if your monitoring system went dark at midnight and you had to reconstruct what happened at 2am from logs alone, could you answer "how many payment requests failed between 2:00am and 2:05am, broken down by failure type"? If the answer is no, you have reactive forensics, not monitoring.

## Prerequisites: Structured Logs with Consistent Fields

Free-text logs support one monitoring pattern: string matching. You can alert when a log line contains the word "error" or the phrase "connection refused". That is the ceiling. You cannot group by error type, compute rates per service, derive latency percentiles, or join log events to traces without structured fields.

Log-based monitoring requires JSON output — or logfmt, or any format your query layer can parse — with stable field names across every service and every deployment. Stable means the same field name carries the same semantic meaning everywhere, every time. `status` in one service meaning HTTP status code and in another meaning a job state is not stable.

These fields are the minimum viable set:

- `level` or `severity` — lowercase enum: `debug`, `info`, `warn`, `error`. Not `ERROR`, not `Error`, not `2`. Pick one convention and enforce it at the logger configuration, not in application code.
- `service` or `app` — the emitting service name, set once at process startup. Not computed per log call, not derived from hostname.
- `timestamp` — ISO 8601 (`2024-01-15T14:22:01.000Z`) or Unix milliseconds. Not a locale-formatted string, not a string that varies by timezone.
- `message` — the human-readable description. Free text is fine here. This is the field humans read; all queryable state lives in other fields.
- `error_type` or `error.type` — on every error event, as a stable string value (`gateway_timeout`, `validation_error`, `rate_limited`). Not buried inside the message string.
- `trace_id` — the W3C trace context trace ID. Required for log-to-trace correlation.

The contrast between what works and what doesn't is direct:

```text
# Free text — string matching only
2024-01-15 14:22:01 ERROR Failed to process payment for user abc123: gateway timeout

# Structured — every field is queryable, groupable, alertable
{"timestamp":"2024-01-15T14:22:01Z","level":"error","service":"payment-api","event":"payment.failed","error_type":"gateway_timeout","gateway":"stripe","user_id_hash":"a3f9c2","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","duration_ms":5003}
```

The free-text version tells a human what happened. The structured version tells a query engine what happened. You need the second form before any of the query patterns below will work.

## Query Strategies

### Rate and Error Counting

The most common log monitoring queries count events over rolling time windows and group by a field. In LogQL (Loki), `count_over_time` does this:

```logql
# Error count over 1-minute windows, grouped by service
sum by (service) (
  count_over_time(
    {job="application"} | json | level="error" [1m]
  )
)
```

That gives you a per-service error count time series. Raw counts are useful for detecting volume spikes. They are misleading when request volume varies — a count of 50 errors means something different at 1,000 requests/minute than at 10,000 requests/minute.

Compute an error ratio instead:

```logql
# Error rate as a fraction of total requests
sum(count_over_time({service="payment-api"} | json | level="error" [5m]))
/
sum(count_over_time({service="payment-api"} [5m]))
```

The denominator counts all log lines from the service, treating each as one request. This only works if you log once per request at a consistent severity level. If you emit multiple log lines per request, normalize the denominator to a specific event type (`event="request.complete"`) rather than total line count.

### Pattern Detection

Aggregate rates miss failure modes that are narrowly scoped. A 0.1% error rate across a service looks fine. A 100% error rate for one specific payment provider, affecting 0.1% of users, also produces 0.1% aggregate error rate — and represents a complete outage for those users.

Field-level pattern queries surface these:

```logql
# Specific error type on a specific service
count_over_time(
  {service="payment-api"} | json | error_type="gateway_timeout" [5m]
) > 3

# Specific HTTP status from a specific upstream dependency
count_over_time(
  {service="checkout"} | json | upstream_service="inventory" | http_status="503" [5m]
) > 0

# Retry storm: one request_id appearing many times
count_over_time(
  {service="order-processor"} | json | request_id="abc123" [5m]
)
```

The retry storm example is illustrative. In practice, you cannot alert on a specific `request_id` value without knowing it in advance. The real pattern is alerting on a derived metric: count requests where the same ID appears more than N times in a window. That requires aggregating first, which is the log-to-metric pattern below.

### Log-to-Metric Derivation

When a metric doesn't exist at the source, derive one from the log stream. This is appropriate when you're working with existing instrumentation you can't change and you need alertable aggregates. It is not a substitute for source instrumentation — the resolution and accuracy of a log-derived metric depends on your logging rate.

In Loki, any metric query over a log stream produces a derived metric. Promote it to a recording rule to materialize it:

```logql
# Error count per error_type per service — suitable as a recording rule
sum by (service, error_type) (
  count_over_time(
    {job="application"} | json | level="error" [1m]
  )
)
```

In the OTel Collector, the `transform` processor with OTTL statements enriches log records before they reach a backend. For deriving metrics from logs at collection time, use the `count_connector`. Both require `otel/opentelemetry-collector-contrib` — the core image does not include OTTL or connectors:

```yaml
# otel-collector-config.yaml (requires otel/opentelemetry-collector-contrib)
processors:
  transform/enrich_logs:
    log_statements:
      - context: log
        statements:
          - set(attributes["log.level"], attributes["severity_text"])

connectors:
  count:
    spanevents:

exporters:
  prometheusremotewrite:
    endpoint: "http://prometheus:9090/api/v1/write"

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [transform/enrich_logs]
      exporters: [otlp/loki]
    metrics:
      receivers: [count]
      exporters: [prometheusremotewrite]
```

Prefer source-side metrics for high-cardinality signals. Log-to-metric derivation is the right pattern when you inherit existing logs you can't instrument further and you need alertable aggregates from them.

### Cardinality Traps

Never filter on unbounded high-cardinality fields directly inside an alert expression. `user_id`, `trace_id`, `request_id`, `session_id` — these fields have millions of distinct values. A LogQL filter like `| json | user_id="specific_value"` runs a full scan across every log line in the queried stream to find that one value. Running this as a recurring alert rule scans the full stream on every evaluation interval.

The rule is: aggregate first, alert on the aggregate. Group by a bounded dimension (`customer_tier`, `account_type`, `region`, `error_type`) rather than a raw identifier. If you need per-entity anomaly detection, pre-compute a log-derived metric grouped by the bounded dimension, and alert when any bucket in that dimension exceeds a threshold.

In Loki specifically: do not put high-cardinality fields in stream labels. Labels define streams — one unique label combination equals one stream. Putting `user_id` or `trace_id` in a label creates millions of streams and makes the Loki index expensive to query and store. These fields belong as parsed attributes (`| json | user_id`), never as label selectors (`{user_id="..."}`).

## Alerting on Logs

### Threshold Alerts vs. Anomaly Detection

A threshold alert fires when a count or rate crosses a fixed value. This works when you know the expected steady state and it stays stable. For a service that processes 1,000 requests/minute consistently, alerting when errors exceed 50/minute is defensible.

For new services or variable-load patterns, a fixed threshold fails in both directions. Calibrated to peak traffic, it fires constantly during normal high-load periods. Calibrated to off-peak, it misses failures at peak. The error count that indicates a real problem at 3am looks routine at noon.

Baseline comparison handles the variable-load case: alert when today's error rate is more than N standard deviations above the equivalent window from the previous week. This self-adjusts to load patterns. Loki does not have built-in anomaly detection. Route through Grafana's ML-based alerting or an external anomaly detection layer to get this behavior. A well-chosen error ratio threshold combined with multi-window evaluation covers most cases without requiring anomaly detection.

### Multi-Condition Alerts

Single-signal alerts produce false positives. An error from the payment service alone warrants investigation. An error from the payment service, plus upstream 503 from the inventory service, plus onset within five minutes of a deployment, is an incident with a probable cause.

Correlating multiple conditions within a single log stream requires that all conditions appear in the same log line. You can do this with field conjunction in LogQL:

```logql
count_over_time(
  {service="checkout"} | json
    | level="error"
    | upstream_service="inventory"
    | upstream_status="503"
  [5m]
) > 0
```

Cross-stream correlation — two separate services — requires working at the alerting layer. Two separate alert rules with a composite condition in Grafana's alert rule editor, or log enrichment in the OTel Collector that merges context from multiple services into a single record before it reaches the backend.

### Latency from Logs

When distributed tracing is not in place, `duration_ms` or `response_time_ms` in log fields gives you latency. LogQL supports percentile approximation over unwrapped log fields:

```logql
quantile_over_time(0.95,
  {service="api-gateway"} | json | unwrap duration_ms [5m]
) by (endpoint)
```

This produces p95 latency per endpoint from logs, with no trace backend required. The limitation is direct: this is a percentile of logged requests, not all requests. If you log at 10% sampling rate for INFO events, you're computing p95 over a 10% sample. For error events logged at 100%, it's accurate. State the sampling rate when publishing these numbers — a p95 derived from 10% of requests is not the same claim as a p95 derived from all requests.

## Retention and Query Cost

Log monitoring needs two retention tiers with different performance profiles.

The hot tier covers active monitoring: real-time queries, alert evaluation, and incident investigation. This tier must serve queries in seconds. Expect 7 to 30 days here, with full indexing. The exact window depends on how long your incident investigation cycles run — if P1 investigations routinely look back 14 days, your hot tier is 14 days.

The cold tier covers compliance and forensics: regulatory audit trails, capacity planning, post-mortems on slow-developing issues. Object storage without a query index is sufficient. Response times in minutes are acceptable. Expect 90 to 365 days, compressed, not indexed for real-time alerting.

Indexing strategy is the main cost lever. In Loki, the label set determines what is indexed. Keep labels to a small set of low-cardinality dimensions: `service`, `environment`, `region`, `job`. Parse high-cardinality fields at query time with `| json`. Every unique label combination creates a separate stream with its own index entry. A label with 10,000 unique values creates 10,000 streams — this is the most reliable way to make a Loki deployment expensive and slow.

In Elasticsearch and OpenSearch, control field mapping explicitly. Fields you filter on in alert queries — `level`, `service`, `error_type`, `http.status_code` — should be `keyword` type (exact match, not analyzed). Text analysis is for full-text search, not monitoring queries. Use index lifecycle management (ILM) to move indices from hot to warm to cold tiers automatically based on age, matching your retention policy.

## Tool Patterns

### Loki + Grafana

Loki's data model: streams (identified by a label set) contain timestamped log lines. Parsing — extracting structured fields from the log line — happens at query time with `| json`, `| logfmt`, or `| pattern`. You do not define a schema at write time. This makes ingestion cheap and schema evolution easy, but it means parsing cost is paid at query time on every alert evaluation.

Alerting in Grafana uses LogQL expressions promoted to alert rules with a threshold and evaluation interval. The expression you write in Explore is the same expression you wire to an alert rule — no translation required. The key operational requirement: the Loki ruler component must be running for server-side alert evaluation. Without the ruler, Grafana falls back to evaluating LogQL queries from the Grafana server process directly. This works at low alert rule counts and short evaluation intervals, but does not scale. If you have more than a handful of log-based alert rules, deploy the ruler.

### CloudWatch Logs Insights

Two alerting paths exist, with different trade-offs.

Metric Filters run at ingest time. A filter pattern matches against incoming log lines and increments a CloudWatch metric. Alert on that metric with a CloudWatch Alarm. Latency is low — the metric updates within seconds of the log line arriving. The constraint: Metric Filters use a simple pattern language, not full SQL. Complex field-level aggregations are not supported.

Scheduled Logs Insights queries run arbitrary SQL on a schedule via EventBridge and Lambda, then push the result to a CloudWatch metric. More expressive, but adds minutes of latency. Use Metric Filters for real-time alerting. Use Logs Insights for investigation and for alert rules where minute-level latency is acceptable.

```sql
-- CloudWatch Logs Insights: error count by status code
fields @timestamp, status_code
| filter level = "ERROR"
| stats count() as error_count by status_code
| sort error_count desc
```

### OpenTelemetry Collector

The Collector is the right place to enrich, filter, and route log streams before they reach a backend. Operating here reduces ingestion cost and improves signal quality upstream of any query or alerting layer.

Drop noisy logs before ingestion to cut storage cost and alert query scan range:

```yaml
processors:
  filter/drop_debug:
    logs:
      log_record:
        - 'severity_number < SEVERITY_NUMBER_INFO'
```

Route error logs to a high-retention, fast-query backend and INFO logs to a short-retention, cheaper backend using the routing connector. Derive aggregated metrics from log fields using the count connector. All connectors and OTTL processors require `otel/opentelemetry-collector-contrib`. The `otel/opentelemetry-collector` core image does not include them.

### Elasticsearch / OpenSearch

Index template design determines monitoring query performance. Define explicit mappings for your monitoring dimensions. Fields used in alert filters (`level`, `service`, `error_type`, `http.status_code`) must be `keyword` type — not `text`, not dynamically mapped. Dynamic mapping guesses field types from the first document Elasticsearch sees for that field. If the first document's `status_code` is `"200"` (a string), the field maps as `text`. Subsequent numeric comparisons behave unexpectedly.

Write your index template before indexing any documents:

```json
{
  "mappings": {
    "properties": {
      "level":       { "type": "keyword" },
      "service":     { "type": "keyword" },
      "error_type":  { "type": "keyword" },
      "http_status": { "type": "keyword" },
      "trace_id":    { "type": "keyword" },
      "duration_ms": { "type": "long" },
      "message":     { "type": "text" },
      "timestamp":   { "type": "date" }
    }
  }
}
```

Set up ILM to move indices through hot, warm, and cold phases by age. Hot phase: primary shards on fast storage, real-time queries. Warm phase: replicas reduced, queries slower but possible. Cold phase: searchable snapshots on object storage, not suitable for alert evaluation. Align phase transitions with your retention tiers.

## What Log-Based Monitoring Doesn't Replace

Infrastructure metrics — CPU, memory, disk I/O, network throughput — have no log equivalent. These signals come from the host or container runtime, not the application. No amount of application logging surfaces a memory leak or a saturated network interface as reliably as a host metric. Use your metrics layer for infrastructure health; logs cover application-layer state.

Distributed traces are a better tool for latency attribution. A log with `duration_ms` tells you a request took 450ms. A trace tells you 380ms of that was in a downstream database call, 40ms was in deserialization, and 30ms was in a Redis cache miss. Deriving latency from logs is an approximation useful when you have no trace backend. Once you have traces, the log-derived latency number is redundant and less accurate.

Use logs for application-layer monitoring: business event tracking, error specifics, dependency failure modes, request-level context. Use metrics for infrastructure aggregates and SLO burn rate computation. Use traces for latency attribution and cross-service request path analysis.

{{< obs-mascot class="druid" quip="You &lsquo;open the logs&rsquo; only after the fire? I am one with the stream — every event a ripple, every error a tremor in the canopy. I felt the gateway timeouts at 2:03am, long before your dashboard so much as stirred. ...stop archiving a living thing. Query it where it flows." >}}
