---
title: "How to Set Up Your First SLO and Burn Rate Alerts"
date: 2026-10-01
draft: false
excerpt: "A step-by-step walkthrough: define an SLI, calculate your error budget, write Prometheus recording rules, and wire up multi-window burn rate alerts that page you before users notice."
readtime: 9
tags: ["SLOs", "Alerting", "Prometheus", "Grafana", "How-to"]
---

Static threshold alerts tell you when a number crossed a line. Burn rate alerts tell you when you're heading for an outage — before you've arrived. The difference matters most at 3am, when you want enough warning to act, not just a notification that it's already too late.

The result is recording rules that track your error budget consumption and alert rules that fire in proportion to how fast you're burning it — before the budget is gone.

The examples use Prometheus and Alertmanager. Grafana Cloud and Mimir run the same PromQL rules as-is; on Datadog the concepts carry over, but you'll rewrite the queries in its own query language.

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
avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) < 0.2
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

Write both numbers down. The 43.2 minutes is the budget in human terms. The 0.001 error ratio is the one the rules use: burn rate is your observed error ratio divided by 0.001.

{{< obs-budget-burn-rates >}}

Burn rate is the multiplier on how fast you're consuming that 43.2 minutes. A burn rate of 1.0 means you're exactly on track to exhaust the budget at the end of 30 days. A burn rate of 14.4 means you'll exhaust the budget in roughly two days. The threshold of ~14.4x is well-established from the Google SRE Workbook: at this rate you're burning about 2% of your monthly budget every hour, demanding immediate action before significant budget damage accumulates.

{{< obs-budget-healthbar >}}

## Step 3 — Pre-Compute the Error Rates Prometheus Will Query

Recording rules pre-compute the error rate at multiple time windows so alert evaluation stays fast. Create `slo_rules.yml` in your Prometheus rules directory:

```yaml
groups:
  - name: slo_checkout_api
    interval: 1m
    rules:
      # 5m — short window for the fast-burn page
      - record: slo:error_rate:checkout_api:5m
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[5m]))

      # 30m — short window for the moderate-burn page
      - record: slo:error_rate:checkout_api:30m
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[30m]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[30m]))

      # 1h — long window for the fast-burn page
      - record: slo:error_rate:checkout_api:1h
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[1h]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[1h]))

      # 6h — long window for the moderate-burn page, short window for the ticket
      - record: slo:error_rate:checkout_api:6h
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[6h]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[6h]))

      # 3d — long window for the slow-leak ticket
      - record: slo:error_rate:checkout_api:3d
        expr: |
          sum(rate(http_requests_total{job="checkout-api", status=~"5.."}[3d]))
          /
          sum(rate(http_requests_total{job="checkout-api"}[3d]))
```

The 3-day rule reads three days of raw samples on every evaluation. That's fine for one service; with many, give that group a slower `interval` (5m is plenty for a ticket) or build it from the 6h rule.

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

The multi-window approach is what separates burn rate alerting from glorified threshold alerting. Each alert requires *two* windows to exceed the threshold at the same time. The long window is the real condition: it only crosses the threshold once a meaningful slice of the budget is gone. The short window checks the burn is still happening, so the alert clears minutes after you fix it instead of hours later. The thresholds and window pairs are the ones in Google's [SRE Workbook](https://sre.google/workbook/alerting-on-slos/).

```yaml
groups:
  - name: slo_alerts_checkout_api
    rules:
      # P0 — Fast burn: error budget exhausted in ~2 days
      # 14.4x burn rate = 14.4 × 0.001 = 1.44% error rate (2% of budget in 1h)
      - alert: CheckoutAPI_FastBurn
        expr: |
          slo:error_rate:checkout_api:1h  > (14.4 * 0.001)
          and
          slo:error_rate:checkout_api:5m  > (14.4 * 0.001)
        labels:
          severity: critical
          slo: checkout_api
        annotations:
          summary: "Checkout API burning error budget at 14.4x — exhausted in ~2d"
          description: >
            Error rate {{ $value | humanizePercentage }} over the last hour, still burning in the last 5m.
            At this rate, monthly error budget exhausted in approximately two days.
          runbook: "https://runbooks.example.com/checkout-api#fast-burn"

      # P1 — Moderate burn: budget exhausted in ~5 days
      # 6x burn rate = 6 × 0.001 = 0.6% error rate (5% of budget in 6h)
      - alert: CheckoutAPI_ModerateBurn
        expr: |
          slo:error_rate:checkout_api:6h  > (6 * 0.001)
          and
          slo:error_rate:checkout_api:30m > (6 * 0.001)
        labels:
          severity: warning
          slo: checkout_api
        annotations:
          summary: "Checkout API burning error budget at 6x — exhausted in ~5 days"
          description: >
            Error rate {{ $value | humanizePercentage }} over the last 6h, still burning in the last 30m.
          runbook: "https://runbooks.example.com/checkout-api#moderate-burn"

      # Ticket — Slow leak: on pace to spend the whole budget (10% of it in 3d)
      - alert: CheckoutAPI_SlowBurn
        expr: |
          slo:error_rate:checkout_api:3d  > (1 * 0.001)
          and
          slo:error_rate:checkout_api:6h  > (1 * 0.001)
        labels:
          severity: ticket
          slo: checkout_api
        annotations:
          summary: "Checkout API spending error budget at 1x+ for 3 days"
          description: >
            Error rate {{ $value | humanizePercentage }} over the last 3d, still above budget pace in the last 6h.
          runbook: "https://runbooks.example.com/checkout-api#slow-burn"
```

There's no `for:` clause on purpose. A `for:` would hold the page back while the condition persists, but the long window already demands a sustained burn: 14.4× for a full hour has spent 2% of the month's budget. Route `severity: ticket` to your ticket queue, not to the pager.

{{< insight lightbulb >}}
**Why two windows per alert?** A long window alone is slow to forgive: after you fix the bug, the 1h error ratio stays over threshold for most of an hour, and the page keeps firing. A short window alone fires on every blip. Together, the long window says enough budget is gone to matter, and the short window says it's still going. Fix the problem and the short window drops within minutes, taking the alert with it.
{{< /insight >}}

## Step 5 — Make Sure It Fires Before You Need It To

A misconfigured alert discovered during an actual incident means debugging your alerting config at the same time you're debugging the outage. Test it now, while stakes are low, by temporarily injecting errors — return 500s from a test endpoint and watch the alert state change in Prometheus:

Navigate to `http://localhost:9090/alerts` in your browser.

You should see `CheckoutAPI_FastBurn` go from `inactive` to `firing` as soon as both windows cross 1.44%. With no `for:` clause there's no `pending` stage. If you return only errors, that takes a few minutes; at a lower injected error rate, it takes longer for the 1-hour ratio to climb.

If it never fires, check that both recording rules are returning values above the threshold. The `and` clause requires both conditions to be simultaneously true — if either window is below the threshold, the alert won't fire.

{{< insight bookmark >}}
**The error budget dashboard.** Add a Grafana panel showing budget consumed over the rolling 30 days, in minutes:

```
43.2 * (
  sum(increase(http_requests_total{job="checkout-api", status=~"5.."}[30d]))
  /
  sum(increase(http_requests_total{job="checkout-api"}[30d]))
) / 0.001
```

That's the 30-day error ratio divided by the 0.1% budget ratio, scaled to the 43.2-minute budget. It reads raw counters rather than averaging the 5m recording rule, so it weights every request equally and doesn't wait 30 days for the rule's history to fill. Seeing "you've consumed 7 of your 43.2 minutes this month" makes the SLO feel real in a way that percentage graphs don't.
{{< /insight >}}

## Error Budget Burn Is Now Observable at Five Time Windows

Your service now has recording rules computing error rates at five time windows, a P0 page that fires when the error budget will be exhausted in about two days, a P1 page for sustained moderate burns, and a ticket for the slow leak. All three carry burn rate context and runbook links in their annotations.

The next piece: making sure these alerts route to the right people via the right channels. That mapping — which severity wakes someone up and which waits until morning — is in [Alert Severity Levels, Rebuilt for Burn Rate](/guides/alert-severity-levels/). And for the thinking behind *why* this model works better than threshold alerting, [SLOs and Error Budgets](/guides/slos-and-error-budgets/) has the full argument.

Pages now carry burn rate context and a runbook link — the information needed to act, not just a notification that something is wrong.

{{< obs-mascot class="wizard" quip="Two windows must align before I name the omen real — the long to prove the wound is deep, the short to prove it still bleeds. A single flicker is a moth, not a fire. But when both burn at 14.4×, I foresee it plainly: two days to ruin. I page. Heed the rune." >}}
