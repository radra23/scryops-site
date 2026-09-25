---
title: "Cardinality Management"
date: 2026-06-07
draft: true
excerpt: "High cardinality is the silent budget killer of metrics systems. How to identify, manage, and prevent cardinality explosions before they take down your Prometheus."
readtime: 9
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

**Unbounded label values.** Any label whose value set is not finite and small is a cardinality risk. Classic offenders: user IDs, email addresses, session tokens, request and correlation IDs, trace IDs, IP addresses. Every new user, session, or request mints a new series. If you need per-entity visibility, that is what logs and traces are for.

```
# ❌ Unbounded — one series per distinct user
http_requests_total{method="GET", user_id="usr_a8f3b2"}

# ✅ Bounded — limited set of known tiers
http_requests_total{method="GET", customer_tier="enterprise"}
```

**Raw paths instead of route templates.** `/api/users/usr-9f2a8b` as a label value is one series per user per endpoint. OTel's HTTP server instrumentation records the route template (`http.route="/api/users/{id}"`), but hand-rolled instrumentation often captures the raw path.

**Free-form error text.** A `message` label holding `"failed to connect to 10.0.1.42:5432"` creates a new series for every address that ever shows up in a connection error. Normalise to a bounded error code or exception type before it becomes a label.

**High-arity enumerations.** Labels with many possible values but a finite set — e.g. a label for each microservice in a large fleet, or each country code — can push cardinality into the thousands for a single metric.

**Label combinations that multiply.** Each additional label multiplies total cardinality. A metric with three labels each taking 10 values generates up to 1,000 series. Adding a fourth label with 10 values takes it to 10,000.

## The Bounded Label Pattern

Every label value should come from a set you could write down today and trust not to grow on its own. Where the real-world value is open-ended, enforce that set in code with an allowlist and a fallback:

```csharp
public static class MetricLabels
{
    private static readonly HashSet<string> AllowedTiers =
        new(StringComparer.OrdinalIgnoreCase) { "free", "starter", "professional", "enterprise" };

    private static readonly HashSet<string> AllowedChannels =
        new(StringComparer.OrdinalIgnoreCase) { "web", "mobile", "api", "partner" };

    public static string NormalizeTier(string? tier) =>
        tier != null && AllowedTiers.Contains(tier) ? tier.ToLowerInvariant() : "unknown";

    public static string NormalizeChannel(string? channel) =>
        channel != null && AllowedChannels.Contains(channel) ? channel.ToLowerInvariant() : "unknown";
}
```

Apply it at the call site, before the value reaches the instrument:

```csharp
OrdersTotal.Add(1,
    new KeyValuePair<string, object?>("tier", MetricLabels.NormalizeTier(request.CustomerTier)),
    new KeyValuePair<string, object?>("channel", MetricLabels.NormalizeChannel(request.Channel)),
    new KeyValuePair<string, object?>("status", status));
```

The `"unknown"` fallback is the important part. A new tier from product or a new channel from a partner integration collapses into one series instead of opening an unbounded set. You see the `unknown` bucket grow, update the allowlist, and Prometheus never notices.

## Cardinality Tracking

To detect cardinality issues before they become incidents, track series counts over time. Prometheus reports on itself:

```promql
# Total active series in the head block
prometheus_tsdb_head_series

# Top 10 metrics by series count
topk(10, count by (__name__) ({__name__=~".+"}))

# Series per scrape job: which service is contributing the most
count by (job) ({__name__=~".+"})

# One metric, broken down by its labels
count by (tier, channel, status) (orders_total)
```

The two `{__name__=~".+"}` queries touch every series in the head block, so they are expensive on a large instance. Run them ad hoc, not on a dashboard that refreshes every 30 seconds. For a cheaper view of the same data, the TSDB status endpoint (`/api/v1/status/tsdb`, also under Status → TSDB Status in the UI) lists the top metric names and label names by series count without running a query.

Alert on growth rate, not just absolute count. A metric that grew from 500 to 5,000 series in a week warrants investigation even if 5,000 is within your current headroom. Record the series count, then compare it with itself a week earlier:

```yaml
groups:
  - name: cardinality
    rules:
      - record: job:http_requests_total:series_count
        expr: count by (job) (http_requests_total)

      - alert: MetricSeriesGrowth
        expr: |
          job:http_requests_total:series_count
            > 2 * (job:http_requests_total:series_count offset 7d)
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "http_requests_total series for {{ $labels.job }} more than doubled in a week"
```

The growth alert only fires once the recording rule has a week of history, so keep an absolute ceiling (for example `job:http_requests_total:series_count > 10000`) alongside it for new metrics.

## Cardinality Impact Assessment

Before adding a new label or metric, estimate its cardinality impact:

**Storage**: Prometheus stores approximately 1–2 bytes per sample after compression. At a 15s scrape interval, 10,000 series adds roughly 50–100 MB/day post-compression. For a 30-day retention window, that is 1.5–3 GB from a single high-cardinality metric.

**Memory**: every active series has an entry in the in-memory head block and its index, and it stays there until the head is compacted, roughly every two hours. A burst of short-lived series (one per request ID, say) keeps costing memory for hours after the traffic that created them stops.

**Query performance**: Queries that aggregate across many series are proportionally slower. A `sum(rate(http_requests_total[5m]))` over 50,000 series will be measurably slower than the same query over 500 series. Record frequently-queried high-cardinality expressions as recording rules to pre-aggregate at scrape time.

**Scrape overhead**: The Prometheus scraper parses every active series on every scrape. Very high cardinality metrics increase the duration and memory cost of the scrape target endpoint.

## Design Rules That Prevent Cardinality Problems

Cheaper to enforce in code review than to clean up afterwards:

**Label values must be enumerable at design time.** If you cannot list every possible value, it is not a label.

**Labels are grouping dimensions, not identities.** `customer_tier` (four values) is a label; `customer_id` (100,000+) is not. The test: would you filter or group by it on a dashboard or in an alert? If you would only ever use it to look up one specific entity, it belongs on a span or a log line.

**Changing a metric's labels is an interface change.** Queries that aggregate with `sum by (...)` keep working when you add a label. Anything matching the exact label set does not: recording rules, `on(...)` joins between metrics, and alerts that assume one series per job can double-count or stop matching. Removing a label silently breaks every query that groups by it. Treat label changes the way you would a column change in a shared table.

{{< insight >}}
**Keep a cardinality budget.** Size a total series budget to your Prometheus instance's memory, then divide it across the metrics you plan to have. With a budget of 1,000,000 series and 100 metrics, the average is 10,000 each. A metric that needs more takes it from the others, or gets redesigned.
{{< /insight >}}

## Remediation

When a metric's cardinality is already too high:

1. **Drop or collapse labels in the Collector.** This is the place to fix it: the raw values survive on spans, and every backend downstream gets clean metrics.
2. **Relabel at scrape time.** `metric_relabel_configs` rewrites or drops labels before Prometheus stores the samples.
3. **Aggregate at the source.** Replace the raw metric with a pre-aggregated one that leaves out the high-cardinality dimension.
4. **Use recording rules.** Keep the raw metric for debugging, and serve dashboards and alerts from a recorded, aggregated series.
5. **Move unbounded dimensions to spans.** Trace attributes can carry user IDs, request URLs, and other high-cardinality context that has no place in metrics.

Dropping a label is not the whole fix: two series that differed only by that label now share a label set. Prometheus rejects the collision as duplicate samples; in the Collector you end up with two data points claiming to be the same series. Whatever you remove, sum what is left.

**In the Collector**, the `metricstransform` processor (in `otelcol-contrib`) does both steps at once. `aggregate_labels` keeps the labels you list and sums across everything else:

```yaml
processors:
  metricstransform/orders:
    transforms:
      - include: orders_total
        action: update
        operations:
          - action: aggregate_labels
            label_set: [tier, channel, status]   # user_id and anything else is summed away
            aggregation_type: sum
```

**At scrape time**, collapse a raw path into its template, or drop a label outright:

```yaml
scrape_configs:
  - job_name: myservice
    metric_relabel_configs:
      # Collapse raw user paths into one route template
      - source_labels: [url_path]
        regex: '/api/users/[^/]+'
        target_label: url_path
        replacement: '/api/users/{id}'
      # Drop a label entirely
      - action: labeldrop
        regex: user_id
```

Relabelling runs per series and cannot sum, so if the collapsed series collide you will see duplicate-sample errors on the scrape. Fix the instrumentation or aggregate in the Collector as well.

**Series already stored** can be removed through the admin API, which needs Prometheus started with `--web.enable-admin-api`:

```bash
curl -X POST \
  'http://prometheus:9090/api/v1/admin/tsdb/delete_series' \
  --data-urlencode 'match[]=orders_total{user_id!=""}'
```

Deletion writes tombstones; the data leaves disk at the next compaction, or immediately with a `POST` to `/api/v1/admin/tsdb/clean_tombstones`.

<!-- TODO: Cover cardinality limits in managed platforms (Datadog custom metrics, Grafana Cloud series limits) -->

- [Metrics Validation](/guides/metrics-validation/) — full validation checklist for metric quality
- [OTel Metrics Instrumentation](/guides/otel-metrics-instrumentation/) — choosing the right instrument type
- [OTel Semantic Conventions](/guides/otel-semantic-conventions/) — standard attribute names that help keep label sets bounded
- [How to Configure Prometheus for Your Service](/howtos/configure-prometheus/) — the Prometheus setup these patterns assume
- [How to Detect Metric Anomalies with Prometheus and Grafana](/howtos/detect-anomalies-with-prometheus/) — anomaly detection gets far more tractable once cardinality is under control
