---
title: "Cardinality Management"
date: 2026-06-07
draft: false
excerpt: "High cardinality is the silent budget killer of metrics systems. How to identify, manage, and prevent cardinality explosions before they take down your Prometheus."
readtime: 7
tags: ["Metrics", "Prometheus", "Observability", "Best Practices"]
---

Prometheus stores every unique combination of label values as a separate time series. A metric with three labels — each taking ten possible values — produces 1,000 time series. If one of those labels is a user ID, and you have 100,000 users, a single metric creates 100,000 time series. Multiply by the number of metrics, and you have a Prometheus instance that runs out of memory before it runs out of useful data.

{{< obs-cardinality-explosion >}}

Cardinality is not a Prometheus implementation detail. It is the fundamental constraint that shapes how you design metrics, which labels you choose, and how you defend a working system against the instrumentation choices of twenty developers working independently.

## What High Cardinality Actually Costs

Prometheus keeps its time series index in memory. Each unique label set — called a fingerprint — occupies memory for as long as the series is active, plus two hours after its last sample (the "lookback window"). A cardinality explosion means memory grows until Prometheus either OOMs or degrades to the point where scrapes start timing out.

The cost compounds. A high-cardinality metric does not just use memory proportional to its series count. It also slows every query that touches it — `rate()`, `sum()`, `histogram_quantile()` — because each evaluation has to iterate more series. A dashboard panel that takes 2 seconds with 10,000 series takes 200 seconds with 1,000,000.

The ceiling is not abstract. In a real Prometheus deployment, cardinality above ~2,000,000 active series on a single instance starts to cause operational problems. Below that, you have headroom. Above that, you are managing symptoms.

{{< obs-cardinality-meter >}}

## Labels That Will Kill You

The labels most likely to cause cardinality explosions are the ones that encode per-entity identifiers. The pattern is the same in every case: the label seems reasonable at the time, it encodes genuinely useful information, and it scales with the entity count rather than with a small, bounded set of values.

**User IDs, session tokens, and device IDs** are the canonical examples. They are always unbounded — every new user, session, or device creates a new series. They should never appear as metric labels. If you need per-user visibility, use logs or traces, which are designed for high-cardinality attributes.

**Raw request IDs and correlation IDs** have the same problem. A correlation ID that traces one request through ten services creates ten new time series for every request.

**Free-form error messages and exception types** can explode in ways that are harder to predict. A `message` label that contains `"failed to connect to 10.0.1.42:5432"` creates a different series for every IP address that ever appears in a connection error. Normalise to bounded error codes before using them as labels.

**Dynamic path segments** in URL labels: `/api/users/usr-9f2a8b` as a label value creates a series per user per endpoint. The OTel AspNetCore instrumentation handles this correctly with route templates (`/api/users/{id}`), but custom instrumentation often captures the raw path.

## The Bounded Label Pattern

The safe design principle is that every label value must come from a bounded set — a set small enough that you could enumerate all its members today and be confident the set will not grow unboundedly.

For labels where the real-world value is unbounded, enforce a bounded set explicitly with an allowlist and a fallback:

```csharp
public static class MetricLabels
{
    private static readonly HashSet<string> AllowedTiers =
        new(StringComparer.OrdinalIgnoreCase)
        {
            "free", "starter", "professional", "enterprise"
        };

    private static readonly HashSet<string> AllowedChannels =
        new(StringComparer.OrdinalIgnoreCase)
        {
            "web", "mobile", "api", "partner"
        };

    public static string NormalizeTier(string? tier) =>
        tier != null && AllowedTiers.Contains(tier) ? tier.ToLowerInvariant() : "unknown";

    public static string NormalizeChannel(string? channel) =>
        channel != null && AllowedChannels.Contains(channel) ? channel.ToLowerInvariant() : "unknown";
}
```

The "unknown" fallback is essential. It ensures that new values — a new tier introduced by product, a new channel from a third-party integration — collapse to a single series rather than creating an unbounded one. You will see a spike in the "unknown" bucket and know to update the allowlist, but Prometheus stays healthy.

Apply this at the call site before recording metrics:

```csharp
OrdersTotal.Add(1,
    new KeyValuePair<string, object?>("tier", MetricLabels.NormalizeTier(request.CustomerTier)),
    new KeyValuePair<string, object?>("channel", MetricLabels.NormalizeChannel(request.Channel)),
    new KeyValuePair<string, object?>("status", status));
```

## Auditing Cardinality in PromQL

Prometheus exposes its own cardinality data through the `/api/v1/label` endpoint and via `prometheus_tsdb_*` metrics. For day-to-day auditing in PromQL:

**Total active series count:**
```promql
prometheus_tsdb_head_series
```

**Top 10 metrics by series count:**
```promql
topk(10,
  count by (__name__) ({__name__=~".+"})
)
```

**Series count for a specific metric broken down by its labels:**
```promql
count by (tier, channel, status) (orders_total)
```

Run the middle query on a cadence — weekly, or after each deployment that adds new instrumentation. It will surface cardinality problems before they become operational incidents. A metric that jumps from 50 series to 5,000 between two audits is a signal that a new label value escaped its bounds.

**Series added by a specific job:**
```promql
count by (job) ({__name__=~".+"})
```

This tells you which scraped service is contributing the most series. Useful when diagnosing an OOM or slow scrape.

## Design Rules That Prevent Cardinality Problems

Rather than reacting to cardinality explosions after they occur, enforce these rules in code review:

Label values must be enumerable at design time. If you cannot write down all possible values of a label, it should not be a label.

Labels encode grouping dimensions, not entity identities. `customer_tier` is a label (four values). `customer_id` is not a label (100,000+ values). The test: would you filter or group by this label in a dashboard or alert? If yes, it is a label. If you would only ever use it to look up one specific entity, it belongs in logs or traces.

Add labels conservatively. Adding a label to an existing metric is a breaking change — it changes the fingerprint, invalidates existing recording rules and alerts, and multiplies the series count. Labels are easier to add initially than to remove later; removing a label is a breaking change for any consumer that depends on it.

{{< insight >}}
**The cardinality budget.** A useful heuristic: budget for a maximum total of 1,000,000 active series across your Prometheus instance. Divide that budget by the number of metrics you plan to instrument. A 100-metric system has ~10,000 series per metric on average. If any one metric needs more, others need less — or you need to redesign the high-cardinality one.
{{< /insight >}}

## When You Already Have a Cardinality Problem

If cardinality has already grown out of control, the tools are limited:

**Drop high-cardinality labels in the Collector** using OTTL before the data reaches Prometheus. This is the right place to normalise or remove labels — it preserves the raw data in traces while keeping metrics clean:

```yaml
processors:
  transform/drop_user_label:
    metric_statements:
      - context: datapoint
        statements:
          - delete_key(attributes, "user_id")
```

**Use metric relabeling in Prometheus** to drop or rewrite label values before storage:

```yaml
scrape_configs:
  - job_name: myservice
    metric_relabel_configs:
      # Drop the raw path label, keep the route template
      - source_labels: [http_route]
        target_label: http_route
        regex: '/api/users/[^/]+'
        replacement: '/api/users/{id}'
```

**Delete the problematic series** via the Prometheus admin API if they are already stored:

```bash
curl -X POST \
  'http://prometheus:9090/api/v1/admin/tsdb/delete_series' \
  --data 'match[]=bad_metric{user_id=~".+"}'
```

The admin API requires `--web.enable-admin-api` at startup.

---

- [How to Configure Prometheus for Your Service](/howtos/configure-prometheus/) — foundational Prometheus setup before applying these patterns
- [How to Detect Metric Anomalies with Prometheus and Grafana](/howtos/detect-anomalies-with-prometheus/) — anomaly detection becomes much more tractable with controlled cardinality

<!-- TODO: Add section on Prometheus remote write and how cardinality costs scale with storage backends -->
<!-- TODO: Add section on adaptive metrics in Grafana Cloud -->

{{< obs-mascot class="barbarian" quip="I added a label. user_id. Then request_id. The dashboard took 200 seconds to load and the bill arrived in a CART pulled by oxen. I cannot cleave a number this large. ...bound your labels to a known set. Spare the cluster." >}}
