---
title: "Metrics Validation: A Quality Gate for Instrumentation"
date: 2026-06-11
draft: true
excerpt: "Adding a metric is the easy part. A metric that uses the wrong type, violates naming conventions, or silently generates 50,000 series is worse than no metric — it degrades the whole system. This guide covers the checks to run before a metric ships."
readtime: 7
tags: ["Metrics", "Observability", "OpenTelemetry", "Prometheus", "Best Practices"]
---

A metric that is wrong in a subtle way is harder to deal with than a metric that is missing. Missing metrics produce gaps in dashboards. Wrong metrics produce incorrect dashboards that look correct. A counter used where a gauge belongs will give you a monotonically increasing line that tells you nothing about the current state. A histogram with one bucket (`le="+Inf"`) gives you count and sum but no distribution. These mistakes are easy to introduce and hard to notice once they're in production.

Validation is the quality gate between "I added a metric" and "this metric is reliable."

## Naming Convention Compliance

Prometheus metric names follow a specific format. Violations produce names that are hard to query, inconsistent with standard exporters, and rejected by some backends.

**Name structure:** `{namespace}_{subsystem}_{name}`

```
# ✅ Valid
http_server_requests_total
process_cpu_seconds_total
go_memstats_heap_alloc_bytes

# ❌ Invalid — hyphens not allowed
http-server-requests-total

# ❌ Invalid — namespace missing, meaning ambiguous
requests_total
```

**Allowed characters:**
- Metric names: `[a-zA-Z0-9:_]` — underscores and colons only; no hyphens
- Label names: `[a-zA-Z0-9_]` — underscores only; labels beginning with `__` are reserved for internal use
- Maximum metric name length: 200 characters

**Suffix conventions** (mandatory for standard types):
- `_total` — counters
- `_seconds`, `_bytes`, `_info` — units should appear as suffixes
- `_created` — optional creation timestamp for counters and histograms
- `_bucket`, `_sum`, `_count` — generated automatically by histograms and summaries; do not define manually

Label names should use lowercase snake_case and describe the dimension, not the value: `http_method`, not `GET`.

## Metric Type Validation

Each instrument type has a contract. Violations of that contract produce nonsensical data.

### Counter

**Contract:** monotonically increasing; resets to zero only on process restart.

| Check | Valid | Invalid |
|---|---|---|
| Value direction | Always increases or stays flat | Decreases between samples |
| Minimum value | 0 after reset | Negative values |
| Reset handling | Jump from large to small value indicates reset | Unexplained zero |

A counter that decreases is either the wrong type (use `UpDownCounter` or Gauge) or a bug. A negative counter value indicates the instrumentation code is subtracting rather than adding.

### Gauge

**Contract:** represents a current value; can increase or decrease; has no implicit direction.

| Check | Valid | Invalid |
|---|---|---|
| Value range | Any real number within stated bounds | Values outside documented min/max |
| Unit | Consistent unit per series | Mixed units (sometimes bytes, sometimes megabytes) |
| Staleness | Updated at appropriate frequency | Static for extended periods without staleness marker |

A gauge that only ever increases is probably a counter. A gauge with no plausible lower bound (queue depth going negative) indicates a bug in the instrumented code.

### Histogram

**Contract:** records a distribution; bucket boundaries determine resolution of percentile estimates.

| Check | Valid | Invalid |
|---|---|---|
| Bucket boundaries | Monotonically increasing, ending in `+Inf` | Missing `+Inf` bucket; non-monotonic boundaries |
| Bucket count | Enough to cover the expected distribution | Single bucket (`+Inf` only) — no distribution |
| Sum and count | Both present and consistent | Sum inconsistent with bucket values |

The most common histogram mistake is using default buckets designed for web service latency (0.005 to 10 seconds) on a metric with a completely different scale — e.g. database query time in microseconds, or job run time in hours. Misconfigured buckets concentrate all observations into the `+Inf` bucket, making percentile estimates useless.

<!-- TODO: Add guidance on histogram bucket boundary selection for different measurement scales -->

## Implementation Checklist

Use this checklist when adding or reviewing a metric.

### Metric Definition

- [ ] Namespace follows conventions (`{namespace}_{subsystem}_{name}`)
- [ ] Name uses only `[a-zA-Z0-9:_]` — no hyphens
- [ ] Name ends with the appropriate type suffix (`_total`, `_seconds`, etc.)
- [ ] Type is appropriate for the measurement (see [OTel Metrics Instrumentation](/guides/otel-metrics-instrumentation/))
- [ ] Units are documented and consistent
- [ ] Description is present and explains what the metric measures

### Labels

- [ ] Label cardinality estimated — no unbounded values (user IDs, URLs, request IDs)
- [ ] Label names use `[a-zA-Z0-9_]` — no hyphens, no `__` prefix
- [ ] Each label dimension is necessary — removing it would lose information needed for alerting or diagnosis
- [ ] Label values come from a bounded, known set

### Collection Configuration

- [ ] Collection interval matches the measurement's expected rate of change
- [ ] Error handling is in place — collection failures are logged or surfaced, not silently swallowed
- [ ] Aggregation settings (histogram buckets, summary quantiles) match the use case

### Performance

- [ ] Estimated series count at target scale is within acceptable bounds (see [Cardinality Management](/guides/cardinality-management/))
- [ ] Collection overhead is not measurable at the service's normal load
- [ ] High-cardinality raw metrics have pre-aggregated recording rules for dashboards and alerts

### Data Quality

- [ ] Values are within expected range for the instrument type (counters non-negative, gauges within documented bounds)
- [ ] The metric updates at expected frequency — a gauge that never changes is likely stale
- [ ] Timestamps are accurate (collected at scrape time, not deferred or batched from an earlier window)

## Update Frequency Validation

A metric that stops updating is a silent failure. The series continues to exist in the backend with its last value; dashboards show a flat line rather than a gap; alerts based on rate-of-change silently stop firing.

To detect staleness:

```
# PromQL: find series with no new samples in 5 minutes
(time() - timestamp(my_metric)) > 300
```

Prometheus marks a series as stale when a scrape target stops returning it. Staleness markers propagate to queries after a configurable lookback window (`--storage.tsdb.min-block-duration`). For metrics from push-based pipelines (Pushgateway, OTel Collector batch exports), staleness detection requires an explicit freshness check.

## Monitoring the Monitoring

The metrics collection pipeline is itself observable. Track these meta-metrics to detect systemic quality issues:

| Meta-metric | What it indicates |
|---|---|
| `prometheus_target_scrape_duration_seconds` | Scrape latency — high values indicate target-side overhead |
| `prometheus_target_scrape_samples_scraped` | Series count per target — sudden jumps indicate cardinality explosion |
| `prometheus_tsdb_head_series` | Total active series in TSDB — proxy for overall cardinality load |
| `prometheus_rule_evaluation_duration_seconds` | Recording/alerting rule evaluation latency — degrades at high cardinality |

Alert on `prometheus_tsdb_head_series` growth rate, not just absolute count. A Prometheus instance approaching its series limit will begin dropping samples silently before it crashes.

<!-- TODO: Add OTel Collector pipeline health metrics (otelcol_receiver_accepted_metric_points, otelcol_exporter_sent_metric_points, drop rates) -->

- [Cardinality Management](/guides/cardinality-management/) — depth on cardinality thresholds and remediation
- [OTel Metrics Instrumentation](/guides/otel-metrics-instrumentation/) — choosing the right instrument type
- [OTel Semantic Conventions](/guides/otel-semantic-conventions/) — standard attribute names for metrics labels
