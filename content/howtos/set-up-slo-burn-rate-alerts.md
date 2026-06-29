---
title: "How to Set Up Your First SLO and Burn Rate Alerts"
date: 2026-05-26
draft: true
excerpt: "A step-by-step walkthrough: define an SLI, calculate your error budget, write Prometheus recording rules, and wire up multi-window burn rate alerts that page you before users notice."
readtime: 9
tags: ["SLOs", "Alerting", "Prometheus", "Grafana", "How-to"]
---

> "The best time to set up burn rate alerts was the day you shipped your service. The second best time is now."
> — An SRE, Paged at 2:47am

Static threshold alerts tell you when a number crossed a line. Burn rate alerts tell you when you're heading for an outage — before you've arrived. The difference matters most at 3am, when you want enough warning to act, not just a notification that it's already too late.

The result is recording rules that track your error budget consumption and alert rules that fire in proportion to how fast you're burning it — before the budget is gone.

The examples use Prometheus and Alertmanager. If you're on Datadog or Grafana Cloud, the recording rule concepts translate directly; the PromQL syntax will differ slightly.

## What you'll need

- Prometheus scraping your service
- A metric that counts request outcomes — a counter with a `status` or `error` label, or an HTTP metrics provider like `opentelemetry-instrumentation-flask` (which emits `http_server_request_duration_seconds` as a histogram)
- Grafana (optional, for dashboards and alert routing)

## Step 1 — Choose What You're Actually Measuring

Here's where most SLO implementations go wrong before they've written a line of config: they pick proxy metrics instead of user-experience metrics.

❌ **Proxy metrics — what most teams start with:**
```
# CPU usage, memory, queue depth — these might correlate with problems,
# but they don't directly measure whether users are getting what they asked for
avg(node_cpu_seconds_total{mode="idle"}) < 0.2
```

✅ **User-experience metrics — what your SLI should measure:**
```
# Requests that completed with a 5xx response (errors)
rate(http_requests_total{status=~"5.."}[5m])
  /
rate(http_requests_total[5m])
```

For OTel-generated metrics, the histogram looks like this:

```
rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m])
  /
rate(http_server_request_duration_seconds_count[5m])
```

Use whatever label your service emits for HTTP status codes — the principle is the same: errors divided by total requests.

## Step 2 — Do the Maths Once

With a 99.9% SLO over a 30-day window, you're allowed 0.1% of requests to fail. In time terms:

- 30 days × 24 hours × 60 minutes × 0.001 = **43.2 minutes** of allowed error budget

Write this number down explicitly. It becomes the denominator for every burn rate calculation that follows.

{{< obs-budget-burn-rates >}}

Burn rate is the multiplier on how fast you're consuming that 43.2 minutes. A burn rate of 1.0 means you're exactly on track to exhaust the budget at the end of 30 days. A burn rate of 14.0 means you'll exhaust the budget in roughly two days. The threshold of ~14x is well-established from the Google SRE Workbook: at this rate you're burning over 1% of your monthly budget every hour, demanding immediate action before significant budget damage accumulates.

{{< obs-budget-healthbar >}}

## Step 3 — Pre-Compute the Error Rates Prometheus Will Query

Recording rules pre-compute the error rate at multiple time windows so alert evaluation stays fast. Create `slo_rules.yml` in your Prometheus rules directory:

```yaml
groups:
  - name: slo_checkout_api
    interval: 1m
    rules:
      # 5-minute window — responsive to fast burns
      - record: slo:error_rate:checkout_api:5m
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[5m]))

      # 30-minute window — for the moderate burn alert
      - record: slo:error_rate:checkout_api:30m
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[30m]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[30m]))

      # 1-hour window — confirms fast burns are sustained
      - record: slo:error_rate:checkout_api:1h
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[1h]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[1h]))

      # 6-hour window — catches slow bleeds
      - record: slo:error_rate:checkout_api:6h
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[6h]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[6h]))
```

Reload Prometheus to pick up the new rules:

```bash
curl -X POST http://localhost:9090/-/reload
```

This endpoint requires Prometheus to be started with the `--web.enable-lifecycle` flag. Without it the call returns a 404 and rules are not reloaded. Alternatively, `kill -HUP $(pgrep prometheus)` works regardless of that flag.

Verify the metrics exist before writing the alert rules:

```bash
curl 'http://localhost:9090/api/v1/query?query=slo:error_rate:checkout_api:5m'
```

## Step 4 — The Alerts That Actually Tell You Something

The multi-window approach is what separates burn rate alerting from glorified threshold alerting. Each alert requires *two* windows to exceed the threshold simultaneously: a short window for responsiveness, a long window for confidence that the burn is real and not a transient spike. Both must be true at once.

```yaml
groups:
  - name: slo_alerts_checkout_api
    rules:
      # P0 — Fast burn: error budget exhausted in ~2 days
      # 14x burn rate = 14 × 0.001 = 1.4% error rate
      - alert: CheckoutAPI_FastBurn
        expr: |
          slo:error_rate:checkout_api:5m  > (14 * 0.001)
          and
          slo:error_rate:checkout_api:1h  > (14 * 0.001)
        for: 2m
        labels:
          severity: critical
          slo: checkout_api
        annotations:
          summary: "Checkout API burning error budget at 14x — exhausted in ~2d"
          description: >
            Error rate {{ $value | humanizePercentage }} over both 5m and 1h windows.
            At this rate, monthly error budget exhausted in approximately two days.
          runbook: "https://runbooks.example.com/checkout-api#fast-burn"

      # P1 — Moderate burn: budget exhausted in ~5 days
      # 6x burn rate = 6 × 0.001 = 0.6% error rate
      - alert: CheckoutAPI_ModerateBurn
        expr: |
          slo:error_rate:checkout_api:30m > (6 * 0.001)
          and
          slo:error_rate:checkout_api:6h  > (6 * 0.001)
        for: 15m
        labels:
          severity: warning
          slo: checkout_api
        annotations:
          summary: "Checkout API burning error budget at 6x — exhausted in ~5 days"
          description: >
            Error rate {{ $value | humanizePercentage }} sustained over 30m and 6h windows.
          runbook: "https://runbooks.example.com/checkout-api#moderate-burn"
```

{{< insight lightbulb >}}
**Why two windows per alert?** The short window (5m or 30m) catches fast-moving incidents quickly. The long window (1h or 6h) filters out transient spikes that resolve on their own. If only the short window fires, it was probably a blip. When both windows exceed the threshold simultaneously, something real is happening — and that's when you want the page.
{{< /insight >}}

## Step 5 — Make Sure It Fires Before You Need It To

A misconfigured alert discovered during an actual incident means debugging your alerting config at the same time you're debugging the outage. Test it now, while stakes are low, by temporarily injecting errors — return 500s from a test endpoint and watch the alert state change in Prometheus:

Navigate to `http://localhost:9090/alerts` in your browser.

You should see `CheckoutAPI_FastBurn` transition:
`inactive` → `pending` (during the `for: 2m` window) → `firing`

If it stays in `pending` and never fires, check that both recording rules are returning values above the threshold. The `and` clause requires both conditions to be simultaneously true — if either window is below the threshold, the alert won't fire.

{{< insight bookmark >}}
**The error budget dashboard.** Once your recording rules are in place, add a Grafana panel showing budget consumption: `43.2 * avg_over_time(slo:error_rate:checkout_api:5m[30d]) / 0.001`. This divides the rolling 30-day average error rate by the 0.1% SLO budget rate to get the effective burn rate, then scales it to budget minutes — giving you "at the rate you've been burning, this is how much of your 43.2-minute budget has been consumed." Seeing the budget expressed as a concrete number — "you've consumed 7 of your 43.2 minutes this month" — makes the SLO model feel real in a way that percentage graphs don't.
{{< /insight >}}

## Error Budget Burn Is Now Observable at Four Time Windows

Your service now has recording rules computing error rates at four time windows, a P0 alert that fires when the error budget will be exhausted in approximately two days, and a P1 alert for sustained moderate burns. Both alerts carry burn rate context and runbook links in their annotations.

The next piece: making sure these alerts route to the right people via the right channels. That mapping — which severity wakes someone up and which waits until morning — is in [Alert Severity Levels, Rebuilt for Burn Rate](/guides/alert-severity-levels/). And for the thinking behind *why* this model works better than threshold alerting, [SLOs and Error Budgets](/guides/slos-and-error-budgets/) has the full argument.

Pages now carry burn rate context and a runbook link — the information needed to act, not just a notification that something is wrong.

{{< obs-mascot class="wizard" quip="Two windows must align before I name the omen real — the short for speed, the long for truth. A single flicker is a moth, not a fire. But when both burn at 14&#215;, I foresee it plainly: two days to ruin. I page. Heed the rune." >}}
