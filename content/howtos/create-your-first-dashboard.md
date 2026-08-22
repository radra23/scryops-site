---
title: "How to Create Your First Observability Dashboard"
date: 2026-06-07
draft: true
excerpt: "From a blank canvas to a dashboard that tells you whether your service is healthy — a step-by-step guide to building a useful first view in Grafana."
readtime: 7
tags: ["Grafana", "Observability", "How-to", "Prometheus"]
---

A blank Grafana instance and a working Prometheus scrape target are all you need. By the end of this how-to you will have a service health dashboard with request rate, error rate, and latency panels that respond dynamically to a service selector — plus deployment annotations that add context when things go wrong.

{{< obs-dashboard-mockup >}}

## Prerequisites

- Grafana 10+ running locally or in your environment
- Prometheus scraping at least one service with standard `http_requests_total` (or equivalent) and histogram metrics
- Basic familiarity with PromQL

## Step 1: Add Prometheus as a Data Source

In Grafana: **Connections → Data sources → Add new data source → Prometheus**.

Set the **Prometheus server URL** to your Prometheus instance (e.g. `http://prometheus:9090` if running in Docker Compose, or `http://localhost:9090` locally). Leave auth settings as-is for a local setup. Click **Save & test** — you should see a green "Data source is working" confirmation.

If you see a connection error, verify Prometheus is reachable from Grafana's network. In Docker Compose setups the hostname is the service name (`prometheus`), not `localhost`.

## Step 2: Create the Dashboard and First Panel

**Dashboards → New → New dashboard → Add visualization**.

Select your Prometheus data source. In the **Query** tab, enter:

```promql
sum(rate(http_requests_total{job="$service"}[5m])) by (code)
```

In the top-right panel editor, set the **Panel title** to `Request Rate`. Leave the visualization type as `Time series`.

Click **Run queries**. If your service is being scraped you will see request rate lines per status code. If the panel is empty, verify the `job` label value matches what Prometheus uses for your service — check `http://localhost:9090/targets` to confirm.

> **Label names vary by instrumentation.** The Prometheus Go client uses `code` for HTTP status. OTel-instrumented services use `http_response_status_code`. Run `http_requests_total` in the Prometheus expression browser and inspect the returned labels before wiring up error-rate panels — a wrong label name produces an empty panel with no error.

## Step 3: Add Template Variables

Template variables turn a static dashboard into a parameterised one — switch services and environments from the dropdowns instead of duplicating the dashboard. Before building more panels, wire up two variables.

Go to **Dashboard settings** (gear icon, top right) **→ Variables → Add variable**.

**Variable 1: service selector**

| Field | Value |
|-------|-------|
| Name | `service` |
| Type | Query |
| Query | `label_values(http_requests_total, job)` |
| Multi-value | ✓ |
| Include All option | ✓ |

**Variable 2: environment**

| Field | Value |
|-------|-------|
| Name | `environment` |
| Type | Query |
| Query | `label_values(http_requests_total, environment)` |
| Multi-value | No |
| Default | `production` |

Save. Return to the dashboard. You will see two dropdowns at the top. Now update the query in your first panel:

```promql
sum(rate(http_requests_total{job=~"$service", environment="$environment"}[5m])) by (code)
```

The `=~` operator matches the multi-select variable using regex union. When the user selects multiple services, Grafana renders the variable as `service-a|service-b` — the regex handles it automatically.

## Step 4: Add an Error Rate Stat Panel

Add a second panel. Set the visualization type to **Stat** — a large current-value display, ideal for at-a-glance health.

```promql
sum(rate(http_requests_total{job=~"$service", environment="$environment", code=~"5.."}[5m]))
/
sum(rate(http_requests_total{job=~"$service", environment="$environment"}[5m]))
* 100
```

In **Field → Unit**, set to `Percent (0-100)`.

In **Field → Thresholds**, set:
- Base: green
- 1% → yellow
- 5% → red

The stat panel colours itself red when error rate exceeds 5%. Title this panel `Error Rate (5xx)`. With colour-coded thresholds, this panel answers "is something wrong?" before you read a single number.

## Step 5: Add a Latency Time Series Panel

Add a third panel. Use `Time series` with two queries for P50 and P99:

```promql
# P50 — in the first query row
histogram_quantile(0.50, sum by (le) (
  rate(http_request_duration_seconds_bucket{job=~"$service", environment="$environment"}[5m])
))

# P99 — in the second query row
histogram_quantile(0.99, sum by (le) (
  rate(http_request_duration_seconds_bucket{job=~"$service", environment="$environment"}[5m])
))
```

Set **Field → Unit** to `seconds (s)`. Give the queries legend labels `P50` and `P99` respectively. Title the panel `Latency`.

If `http_request_duration_seconds_bucket` does not exist for your service, check what histogram name is exposed — common alternatives are `request_duration_seconds_bucket` or a service-specific prefix. A histogram exposes three series: `_bucket`, `_count`, and `_sum` — `histogram_quantile` only needs the `_bucket` series (it computes quantiles from the `le` labels); `_count` and `_sum` are unrelated to quantile computation and are used separately, for computing averages (e.g. `rate(x_sum)/rate(x_count)`).

## Step 6: Add Deployment Annotations

Annotations are vertical marker lines on time series panels — the kind you see on production dashboards that say "deploy at 14:32." They make it immediately obvious whether a behaviour change coincides with a deployment, without manually cross-referencing a deployment log.

{{< obs-dashboard-annotation >}}

Go to **Dashboard settings → Annotations → Add annotation query**.

| Field | Value |
|-------|-------|
| Name | `Deployments` |
| Data source | Prometheus |
| Expr | `changes(kube_deployment_status_observed_generation{namespace="$environment"}[2m]) > 0` (requires `kube-state-metrics`) |
| Title | `{{deployment}}` |
| Icon color | Blue |

If you are not running Kubernetes, substitute a metric your deployment pipeline writes. A common alternative using Pushgateway:

```promql
changes(deployment_timestamp_seconds{job=~"$service"}[2m]) > 0
```

After saving, deploy your service. A blue annotation line will appear on all time series panels at the exact moment the metric changes.

## Step 7: Arrange the Layout

Arrange panels with this hierarchy so the dashboard communicates in five seconds:

1. **Top row** — Stat panels (error rate, current request rate). These answer "is something wrong?" at a glance.
2. **Middle row** — Time series panels (request rate over time, latency). These answer "when did this start?"
3. **Bottom row** — Tables or detailed breakdowns for drill-down work.

{{< obs-dashboard-layout >}}

In Grafana, panels are dragged by their title bar and resized from the bottom-right corner. The grid is 24 units wide. Three stat panels at 8 units each fills the top row neatly.

{{< insight bookmark >}}
**The dashboard answers three on-call questions.** Is something wrong right now — error rate stat. When did it start — request rate and latency trends. What changed at that moment — deployment annotations.
{{< /insight >}}

{{< obs-mascot class="barbarian" quip="BEFORE THE DASHBOARD: Conan reads ten thousand log lines BY HAND. Uphill. In the snow. AFTER THE DASHBOARD: three panels. Red means bad. Conan is free now. Conan is also, quietly, a little sad about it. Conan is NOT going back." caption="Conan the Bawkbarian would lay down his life for your error-rate stat panel." >}}

- [Set Up SLO Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) — define error budgets and alert before they run out
- [Alert Fatigue Is an Observability Problem](/articles/alert-fatigue-is-an-observability-problem/) — why alerting on the right signal matters more than fewer thresholds
- [Detect Metric Anomalies with Prometheus and Grafana](/howtos/detect-anomalies-with-prometheus/) — moving beyond static thresholds with trend-based detection
