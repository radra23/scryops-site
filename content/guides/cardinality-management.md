---
title: "Cardinality Management"
date: 2026-06-07
draft: true
excerpt: "High cardinality is the silent budget killer of metrics systems. How to identify, manage, and prevent cardinality explosions before they take down your Prometheus."
readtime: 6
tags: ["Metrics", "Prometheus", "Observability"]
---

Cardinality is the number of unique time series a metric generates. Each unique combination of label values produces a separate series. A `http_requests_total` metric with labels `{method, status, route}` generates one series per distinct (method, status, route) triple observed. With 4 HTTP methods, 10 status codes, and 500 routes that is 20,000 series — before you add a second service, a second environment, or a per-user label.

That number matters because Prometheus (and equivalent backends) stores, indexes, and evaluates every active series. Cardinality does not just affect storage; it degrades query performance, increases scrape overhead, and can OOM a Prometheus instance entirely at high enough volumes.

## Cardinality Thresholds

The thresholds below are practical starting points for a label-value combination count per metric:

| Count | Severity | Action |
|---|---|---|
| < 100 | Healthy | No action |
| 100 – 1,000 | Warning | Review label design; is every dimension necessary? |
| 1,000 – 10,000 | High | Actively remediate; set recording rules to pre-aggregate |
| > 10,000 | Critical | Block new series; incident-level response |

These are calibrated for a mid-sized Prometheus deployment. Very large installations (federated, Thanos, Cortex) can tolerate higher absolute counts, but the growth rate matters more than the absolute value at scale: a metric that doubles its series count week-over-week is a problem regardless of where it starts.

## What Drives High Cardinality

The most common sources of cardinality explosion, in rough order of frequency:

**Unbounded label values.** Any label whose value set is not finite and small is a cardinality risk. Classic offenders: user IDs, email addresses, request URLs with path parameters (e.g. `/users/12345/orders` as a raw path label), trace IDs, session tokens, IP addresses.

```
# ❌ Unbounded — one series per distinct user
http_requests_total{method="GET", user_id="usr_a8f3b2"}

# ✅ Bounded — limited set of known tiers
http_requests_total{method="GET", customer_tier="enterprise"}
```

**High-arity enumerations.** Labels with many possible values but a finite set — e.g. a label for each microservice in a large fleet, or each country code — can push cardinality into the thousands for a single metric.

**Label combinations that multiply.** Each additional label multiplies total cardinality. A metric with three labels each taking 10 values generates up to 1,000 series. Adding a fourth label with 10 values takes it to 10,000.

## Cardinality Tracking

To detect cardinality issues before they become incidents, track unique label combinations per metric over time:

```
# Prometheus: count active time series per metric name
count by (__name__) ({__name__=~".+"})

# Count series for a specific metric
count(http_requests_total)

# Series count over time (use recording rule for efficiency)
record: job:http_requests_total:series_count
expr: count(http_requests_total) by (job)
```

Alert on growth rate, not just absolute count. A metric that grew from 500 to 5,000 series in a week warrants investigation even if 5,000 is within your current headroom.

```yaml
# Alert on rapid series growth
- alert: HighCardinalityMetric
  expr: count(http_requests_total) > 1000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "http_requests_total has {{ $value }} active series"
```

## Cardinality Impact Assessment

Before adding a new label or metric, estimate its cardinality impact:

**Storage**: Prometheus stores approximately 1–2 bytes per sample after compression. At a 15s scrape interval, 10,000 series adds roughly 50–100 MB/day post-compression. For a 30-day retention window, that is 1.5–3 GB from a single high-cardinality metric.

**Query performance**: Queries that aggregate across many series are proportionally slower. A `sum(rate(http_requests_total[5m]))` over 50,000 series will be measurably slower than the same query over 500 series. Record frequently-queried high-cardinality expressions as recording rules to pre-aggregate at scrape time.

**Scrape overhead**: The Prometheus scraper parses every active series on every scrape. Very high cardinality metrics increase the duration and memory cost of the scrape target endpoint.

## Remediation

When a metric's cardinality is already too high:

1. **Drop high-cardinality labels via relabeling** — use `metric_relabel_configs` to drop or replace the offending label at the Collector or scrape level.
2. **Aggregate at the source** — replace the raw metric with a pre-aggregated one that drops the high-cardinality dimension.
3. **Use recording rules** — keep the raw high-cardinality metric for debugging but satisfy dashboards and alerts from a recorded, aggregated series.
4. **Move unbounded dimensions to spans** — trace attributes can carry user IDs, request URLs, and other high-cardinality context that has no place in metrics.

<!-- TODO: Add Prometheus metric_relabel_configs examples for dropping labels -->
<!-- TODO: Cover cardinality limits in managed platforms (Datadog custom metrics, Grafana Cloud series limits) -->
<!-- TODO: Cover OTel Collector cardinality-limiting transform processor patterns -->

- [Metrics Validation](/guides/metrics-validation/) — full validation checklist for metric quality
- [OTel Metrics Instrumentation](/guides/otel-metrics-instrumentation/) — choosing the right instrument type
- [OTel Semantic Conventions](/guides/otel-semantic-conventions/) — standard attribute names that help keep label sets bounded
