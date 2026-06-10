---
title: "How to Detect Metric Anomalies with Prometheus and Grafana"
date: 2026-06-10
draft: true
excerpt: "Move beyond static thresholds by using Prometheus recording rules and Grafana ML to detect anomalous patterns in your metrics — without deploying a separate ML platform."
readtime: 7
tags: ["AIOps", "Prometheus", "Grafana", "Alerting", "How-to"]
---

Static thresholds alert when a metric crosses a fixed line. Anomaly detection alerts when a metric behaves in a way that deviates from its own history. The two are not interchangeable: a threshold knows nothing about whether today's 15% error rate is normal for a Sunday afternoon or a sign of something breaking.

This how-to covers the approaches available in Prometheus and Grafana — starting with the simplest (trend-based prediction) and building toward seasonal baseline detection.

## Approach 1: Trend-Based Alerting with `predict_linear()`

`predict_linear()` extrapolates where a metric is heading based on its recent trajectory. It is not machine learning — it is linear regression over a time window. But for slowly degrading systems (memory leaks, disk fill, connection pool exhaustion), it is the right tool: simple, interpretable, and available in any Prometheus installation without plugins.

The function signature:

```promql
predict_linear(metric[range], seconds_forward)
```

It takes the metric's values over `[range]`, fits a line to them, and returns the predicted value `seconds_forward` from now.

### Disk exhaustion alert

The canonical `predict_linear` use case: alert on disk usage that will hit capacity within 4 hours, based on the fill rate over the last 6 hours.

```promql
predict_linear(node_filesystem_avail_bytes{job="node-exporter"}[6h], 4 * 3600) < 0
```

The threshold is `< 0` because `avail_bytes` is positive — when `predict_linear` forecasts it going negative, you are predicted to run out. In a Prometheus alerting rule:

```yaml
groups:
  - name: disk-prediction
    rules:
      - alert: DiskWillFillIn4Hours
        expr: |
          predict_linear(
            node_filesystem_avail_bytes{job="node-exporter", fstype!="tmpfs"}[6h],
            4 * 3600
          ) < 0
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Disk {{ $labels.device }} on {{ $labels.instance }} predicted to fill in <4h"
          description: |
            Current fill rate extrapolated from last 6 hours.
            Take action before the disk fills: clear logs, expand volume, or investigate runaway writes.
```

The `for: 15m` guard prevents alerts from misfiring on short-term spikes. `predict_linear` only becomes reliable when the trend has been stable for a meaningful window — a 15-minute confirmation requirement discards transient noise.

### Error rate trend alerting

The same pattern applies to any metric with a directional signal. This alert fires when the error rate is trending toward the SLO threshold 1 hour out:

```promql
predict_linear(
  rate(http_requests_total{status=~"5.."}[5m])[30m:],
  3600
)
/
predict_linear(
  rate(http_requests_total[5m])[30m:],
  3600
)
> 0.05
```

The `[30m:]` subquery syntax materialises the per-minute rate into a range vector so `predict_linear` has enough data points to fit a line.

### Visualising the prediction in Grafana

To show the current metric and its predicted trajectory on a single panel, use three queries:

```promql
# Query A: current error rate (solid line)
rate(http_requests_total{job=~"$service", status=~"5.."}[5m])
/ rate(http_requests_total{job=~"$service"}[5m]) * 100

# Query B: predicted error rate 1h from now (dashed line, plotted as a single point)
predict_linear(
  rate(http_requests_total{job=~"$service", status=~"5.."}[5m])[30m:], 3600
)
/ predict_linear(
  rate(http_requests_total{job=~"$service"}[5m])[30m:], 3600
) * 100

# Query C: SLO threshold at 5% (fixed red reference line)
vector(5)
```

In the panel editor, set Query B's **Line style** to `Dashed` and Query C's line **Color** to red. The panel shows where the metric is, where it is heading, and the threshold it should not cross.

## Tuning Considerations

`predict_linear()` has two variables: the historical window and the forward horizon. Their relationship matters:

A **short window with a long horizon** is highly sensitive to recent spikes and produces false positives on transient load. A **long window with a short horizon** is stable but slow to detect fast-moving degradation. The rule of thumb: the historical window should be at least 3× the forward horizon for a meaningful fit. A 4-hour prediction should be grounded in at least 12 hours of history.

If your metric is noisy, smooth it before passing to `predict_linear`. A rate over a longer window (e.g. `rate(...[15m])` instead of `rate(...[5m])`) reduces variance at the cost of some recency.

<!-- TODO: Add Approach 2 — Z-score anomaly detection with PromQL recording rules -->
<!-- TODO: Add Approach 3 — Grafana ML plugin (machine-learning-powered seasonal baselines) -->
<!-- TODO: Add section on evaluating detector quality: false positive and false negative rates -->
<!-- TODO: Add guidance on when to escalate to a dedicated ML platform -->
