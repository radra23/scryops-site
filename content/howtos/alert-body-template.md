---
title: "The Alert Body Template"
date: 2026-10-03
draft: false
url: "/alert-body-template/"
excerpt: "A copy-paste alert body that answers four questions before the on-call has to ask: what's broken, how fast it's getting worse, what's already been checked, and the first three steps."
readtime: 5
tags: ["Alerting", "On-Call", "SLOs", "Prometheus", "How-to"]
---

Every alert should answer four questions before the on-call has to ask them. This page gives you the template I use: a plain-text version you can paste into any tool, a Prometheus rule that fills it in automatically, and an Alertmanager receiver that renders it in Slack.

The reasoning behind it is in [An Alert Without a Next Step Is Just Noise](/articles/alert-design-principles/). This page is the part you copy.

## The four questions

| Question | Field | What good looks like |
|---|---|---|
| What's broken? | `summary`, `impact` | The service, the operation and the user-facing effect. Not the rule name. |
| How fast is it getting worse? | `burn_rate`, `budget` | Burn rate, budget spent, and time until it runs out at this pace. |
| What's already been checked? | `recent_changes`, `related` | The last deploy, other alerts firing, and whether this has happened before. |
| What are the first three steps? | `first_steps`, `runbook_url` | Commands or checks in order, and a link to the exact runbook section. |

If you can't fill in a field, that's a finding. An alert without first steps means nobody has traced the path from this metric to a fix yet.

## The template

Paste this into your alert description, PagerDuty details or incident tool, and replace the `[BRACKETS]`.

```text
[SEVERITY] [SERVICE] DEGRADED: [user-facing effect in plain words]

Impact:         [~N users/min] affected by [what they experience]
SLO status:     [X]% of the [window] error budget spent; burn rate [N]x; runs out in ~[N]h at this pace
First seen:     [HH:MM UTC] ([N] minutes ago)

Recent changes:
  - [service vX.Y.Z deployed HH:MM UTC] ([N] min before first seen)
  - [other services currently alerting, or "none"]

First steps:
  1. [First check or command]
  2. [If that confirms the cause: the fix or rollback]
  3. [If not: Runbook -> [page] -> section [N]]

Runbook:        [https://runbooks.example.com/page#section]
Dashboard:      [link pre-filtered to this service and time window]
Trace sample:   [link to one failing trace]
```

Here it is filled in for a real-shaped incident: a 99% SLO, so a 1% error budget, with errors at 8.3%.

```text
[P1] PAYMENT SERVICE DEGRADED: checkout payments failing

Impact:         ~420 users/min see a failed payment at checkout
SLO status:     23% of the monthly error budget spent; burn rate 8.3x; runs out in ~67h at this pace
First seen:     02:14 UTC (11 minutes ago)

Recent changes:
  - payment-api v2.4.1 deployed 02:08 UTC (6 min before first seen)
  - No other services currently alerting

First steps:
  1. Check the rollout: kubectl rollout status deploy/payment-api
  2. If the deploy is the cause: kubectl rollout undo deploy/payment-api
  3. If not: Runbook -> payment-errors -> section 3 (gateway timeouts)

Runbook:        https://runbooks.example.com/payment-errors#section-3
Dashboard:      https://grafana.example.com/d/payment?var-service=payment-api&from=now-1h
Trace sample:   https://jaeger.example.com/trace/abc123def456
```

The arithmetic: 8.3% errors against a 1% budget is a burn rate of 8.3x. At that rate a full 30-day budget lasts 30 / 8.3 = about 3.6 days, or 87 hours. With 77% of the budget left, that's about 67 hours.

8.3x is under the 14.4x fast-burn threshold in the rule below, so that rule wouldn't page for this incident. The slower pair the Google SRE Workbook runs alongside it would: 6x over both the last 6 hours and the last 30 minutes. The rules below show the fast-burn half; add the 6x pair the same way, with 6-hour and 30-minute recording rules.

## Prometheus: fill it in automatically

Most of the template can come from the alert rule itself. These rules assume your services export the OpenTelemetry HTTP server metric, which Prometheus exposes as `http_server_request_duration_seconds`, with `service.name` mapped to the `job` label. Change the `job` value, the SLO target and the links to match your setup.

```yaml
groups:
  - name: payment-api-slo
    rules:
      # Error ratio over each window the alert and annotations need.
      - record: slo:payment_api_errors:ratio_rate5m
        expr: |
          sum(rate(http_server_request_duration_seconds_count{job="payment-api", http_response_status_code=~"5.."}[5m]))
          /
          sum(rate(http_server_request_duration_seconds_count{job="payment-api"}[5m]))
      - record: slo:payment_api_errors:ratio_rate1h
        expr: |
          sum(rate(http_server_request_duration_seconds_count{job="payment-api", http_response_status_code=~"5.."}[1h]))
          /
          sum(rate(http_server_request_duration_seconds_count{job="payment-api"}[1h]))
      - record: slo:payment_api_errors:ratio_rate30d
        expr: |
          sum(rate(http_server_request_duration_seconds_count{job="payment-api", http_response_status_code=~"5.."}[30d]))
          /
          sum(rate(http_server_request_duration_seconds_count{job="payment-api"}[30d]))

      # Page on a fast burn: 14.4x over both the last hour and the last 5 minutes (99% SLO = 0.01 budget).
      - alert: PaymentApiErrorBudgetFastBurn
        expr: |
          slo:payment_api_errors:ratio_rate1h > (14.4 * 0.01)
          and
          slo:payment_api_errors:ratio_rate5m > (14.4 * 0.01)
        labels:
          severity: P1
          service: payment-api
          team: payments
        annotations:
          summary: "PAYMENT SERVICE DEGRADED: checkout payments failing"
          impact: "{{ $value | humanizePercentage }} of payment requests failing over the last hour"
          burn_rate: >-
            {{ with query "slo:payment_api_errors:ratio_rate1h / 0.01" }}{{ . | first | value | printf "%.1f" }}x{{ end }}
          budget: >-
            {{ with query "slo:payment_api_errors:ratio_rate30d / 0.01" }}{{ . | first | value | humanizePercentage }} of the 30-day budget spent{{ end }}
          recent_changes: "Check the deploy log: https://deploys.example.com/payment-api"
          first_steps: |
            1. Check the rollout: kubectl rollout status deploy/payment-api
            2. If the last deploy is the cause: kubectl rollout undo deploy/payment-api
            3. If not: runbook section 3 (gateway timeouts)
          runbook_url: "https://runbooks.example.com/payment-errors#section-3"
          dashboard: "https://grafana.example.com/d/payment?var-service=payment-api&from=now-1h"
```

Three details that are easy to get wrong:

- `$value` is the value of the alert expression, here the 1-hour error ratio. It isn't the burn rate. The `burn_rate` annotation divides the ratio by the budget with a `query` call so the number on the page means what it says.
- A 14.4x burn on a 30-day budget empties it in about 2.1 days, not 2 hours. It pages because at that pace the budget is gone within days, not because it's gone already.
- A `[30d]` range is expensive to evaluate on every cycle. It's fine for a handful of services; at scale, derive the 30-day ratio from the shorter recording rules or evaluate it in a slower rule group.

The rule can't know what was deployed. If you record deploys as a metric or as Grafana annotations, link to them in `recent_changes`. If you don't, a link to the deploy log is the honest minimum.

## Alertmanager: render it in Slack

This receiver turns the annotations above into the template layout. It assumes `slack_api_url` is set in the `global` section.

```yaml
receivers:
  - name: oncall-slack
    slack_configs:
      - channel: "#oncall"
        send_resolved: true
        title: '[{{ .CommonLabels.severity }}] {{ .CommonAnnotations.summary }}'
        text: |-
          {{ range .Alerts }}
          *Impact:* {{ .Annotations.impact }}
          *SLO status:* {{ .Annotations.budget }}; burn rate {{ .Annotations.burn_rate }}
          *First seen:* {{ .StartsAt.Format "15:04 MST" }}
          *Recent changes:* {{ .Annotations.recent_changes }}
          *First steps:*
          {{ .Annotations.first_steps }}
          *Runbook:* {{ .Annotations.runbook_url }}
          *Dashboard:* {{ .Annotations.dashboard }}
          {{ end }}
```

Grafana-managed alerts work the same way: put the fields in the rule's annotations (`summary`, `description` and `runbook_url` are built in, and you can add your own) and reference them in a notification template.

## Before you ship an alert

- The summary names the service and the user-facing effect, not the rule.
- The page includes the burn rate and how long the budget lasts at this pace.
- `recent_changes` links to something real.
- The first three steps are written down, in order.
- The runbook link goes to a section, not a page.
- Someone who has never seen this alert could start diagnosing from the body alone.

If an alert can't pass this list, it isn't ready to wake anyone up.
