---
title: "Set Up Log-Based Alerting with Loki and Grafana"
date: 2026-06-10
draft: true
excerpt: "Wire a Loki log stream into a Grafana alert rule that fires on error rate, specific error codes, or a pattern your metrics don't capture. Covers ingestion verification, LogQL query patterns, notification routing, and end-to-end testing."
readtime: 7
tags: ["Logs", "Observability", "Alerting", "Grafana", "How-to"]
---

Metrics alert on rates. Logs alert on specifics. If you need to fire when a particular error code appears more than N times per minute — or when a specific dependency starts failing — and you don't have a metric for it, the log stream is what you have.

The result is a Grafana alert rule backed by a LogQL query, routing to PagerDuty or Slack based on severity labels, with a tested notification payload that includes a runbook link.

{{< mermaid >}}
flowchart LR
    app["Service logs<br/>(structured JSON)"] --> agent["Alloy<br/>(log shipper)"]
    agent --> loki[("Loki")]
    loki --> rule["Grafana alert rule<br/>LogQL + threshold"]
    rule -->|severity=critical| pd["PagerDuty (P1)"]
    rule -->|severity=warning| slack["Slack"]
    style rule fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF
    style pd fill:#2A1414,stroke:#CD384B,color:#FF6060
    style slack fill:#2A2410,stroke:#D4820A,color:#F5A623
{{< /mermaid >}}

## Prerequisites

- Loki running and receiving logs (Docker Compose setup below if you need it)
- Grafana with the Loki data source configured
- Logs are structured JSON with at minimum a `level` field and a `service` field

## Verify Log Ingestion

Open Grafana → Explore → select Loki as the data source. Run a label query to confirm streams exist:

```logql
{service="payment-api"}
```

If no results come back, Promtail or Alloy is not running, or the target path in the scrape config does not match where your application writes logs. The stream selector must match labels in your scrape config exactly — `service` not `app` if your config uses `service`.

To confirm JSON parsing works, add the `json` parser:

```logql
{service="payment-api"} | json
```

Fields parsed from JSON appear in the log line detail panel on the right. If you see `level`, `error_type`, and other structured fields listed as detected fields, parsing is working. If you see nothing, the logs are not valid JSON — check whether your application is writing structured output or mixing plain text with JSON lines.

## Write the LogQL Detection Query

Pick the pattern that matches your failure condition.

**Pattern 1: Error rate threshold**

```logql
sum(count_over_time({service="payment-api"} | json | level="error" [1m]))
```

This counts error log lines per minute across all instances of `payment-api`. Use it when you want to alert on sustained error volume — for example, more than 10 errors per minute for two consecutive minutes.

**Pattern 2: Specific error type**

```logql
sum(count_over_time({service="payment-api"} | json | error_type="gateway_timeout" [5m]))
```

Replace `error_type="gateway_timeout"` with any field-value pair from your log schema. This fires on a specific failure condition, not just any error — useful when one error type carries more operational weight than others. A single `gateway_timeout` may warrant a page where a hundred `validation_error` entries do not.

**Pattern 3: Dependency failure**

```logql
sum(count_over_time({service="checkout"} | json | upstream_service="inventory" | level="error" [5m]))
```

Scopes to errors attributed to a specific upstream. Fire this when inventory is down, not when anything in checkout is misbehaving. The distinction keeps checkout on-call from chasing a problem that belongs to the inventory team.

Test each query in Grafana Explore before wiring it into an alert rule. Switch from "Logs" to "Metrics" mode using the toggle in the query builder — the graph view shows you the rate over time and lets you tune the time window and threshold before committing to an alert definition.

## Create the Alert Rule in Grafana

Navigate to Grafana → Alerting → Alert Rules → New Alert Rule.

**Query:** Paste your LogQL query from the previous step. Set the data source to Loki.

**Expression:** Add a "Threshold" expression. Set the condition to `IS ABOVE 5`. Adjust the threshold to your failure tolerance — for a specific error type you never expect to see, even `IS ABOVE 0` is appropriate.

**Evaluation group:** Set the evaluation interval to `1m`. Set the pending period to `2m`. The pending period requires the condition to hold continuously before the alert transitions to Firing — it absorbs transient spikes that resolve on their own. For critical failures where any occurrence matters, set the pending period to `0`.

**Labels:** Add `service=payment-api` and either `severity=warning` or `severity=critical`. These labels drive notification routing in the next step — they are not cosmetic.

**Annotations:** Add a `summary` annotation describing what fired, for example:

```
payment-api error rate exceeded threshold ({{ $value }} errors in last 1m)
```

Add a `runbook_url` annotation pointing to the runbook for this alert. Both annotations appear in the notification body. A notification without a runbook link forces the on-call engineer to hunt for context at 3am.

Save the rule.

## Configure the Notification Channel

Navigate to Grafana → Alerting → Contact Points → Add Contact Point.

**PagerDuty:**

- Integration: PagerDuty
- Integration Key: your Events API v2 service integration key
- Severity: use the "Override severity" option to map the `severity=critical` label to P1 and `severity=warning` to P2

**Slack:**

- Integration: Slack
- Webhook URL: your Slack app incoming webhook URL
- Title template:

```
{{ .Labels.service }} — {{ .Annotations.summary }}
```

- Message body: include `{{ .Annotations.runbook_url }}` so the runbook link appears in every notification without requiring the engineer to navigate anywhere

After creating the contact points, set a notification policy that routes by severity label. Navigate to Alerting → Notification Policies and add two matchers:

- `severity=critical` → PagerDuty contact point
- `severity=warning` → Slack contact point

Without this policy, all alerts go to the default contact point regardless of severity. The label-based routing is what makes the PagerDuty escalation intentional rather than universal.

## Test the Alert End to End

Generate a log line that matches your query condition. The simplest path is injecting directly into Loki via the push API:

```bash
curl -X POST http://localhost:3100/loki/api/v1/push \
  -H "Content-Type: application/json" \
  -d '{
    "streams": [{
      "stream": {"service": "payment-api"},
      "values": [[
        "'"$(date +%s%N)"'",
        "{\"level\":\"error\",\"error_type\":\"gateway_timeout\",\"message\":\"test\"}"
      ]]
    }]
  }'
```

Triggering a real error path confirms end-to-end log emission rather than just the alert pipeline.

In Grafana → Alerting → Alert Rules, watch the alert state transition: Normal → Pending (condition met, waiting for the pending period) → Firing. If the alert stays in Normal after the condition is met, check that the Loki ruler component is running. Without the ruler, Grafana evaluates alert queries directly, and query load or misconfiguration can cause evaluation lag that masks the state transition.

Once the alert reaches Firing, confirm the notification arrived in your contact point. Check the payload for the `runbook_url` annotation and the `service` label. If they are missing, the annotation template has a syntax error — Grafana drops the field silently rather than failing the notification.

## Adapting the Query to Your Stack

**High-cardinality fields:** Do not filter on `user_id`, `trace_id`, or `request_id` in an alert query. These fields cause Loki to scan every log line against a unique value. Aggregate first, then alert on the aggregate:

```logql
sum by (error_type) (
  count_over_time({service="payment-api"} | json | level="error" [5m])
) > 5
```

**Multi-service correlation:** Two alert rules with a composite condition in Grafana (A AND B both firing) is the cleanest approach for cross-service alerts. Single-query cross-stream correlation in LogQL requires both services to emit to the same Loki stream, which undermines label-based partitioning and makes stream cardinality harder to control.

**Rate of change instead of absolute count:** When baseline request volume varies significantly, alerting on an absolute error count produces both false positives at high volume and false negatives at low volume. Alert on the error fraction instead:

```logql
(
  sum(count_over_time({service="payment-api"} | json | level="error" [5m]))
  /
  sum(count_over_time({service="payment-api"} [5m]))
) > 0.05
```

This fires when more than 5% of log lines are errors — independent of request volume. Set the threshold based on your service's normal error floor.

## Docker Compose Quickstart

Minimal local setup for Loki, Promtail, and Grafana:

```yaml
# docker-compose.yaml
services:
  loki:
    image: grafana/loki:3.0.0
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:3.0.0
    volumes:
      - /var/log:/var/log:ro
      - ./promtail-config.yaml:/etc/promtail/config.yaml
    command: -config.file=/etc/promtail/config.yaml
    depends_on:
      - loki

  grafana:
    image: grafana/grafana:11.0.0
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_FEATURE_TOGGLES_ENABLE=alertingSimplifiedRouting
    depends_on:
      - loki
```

```yaml
# promtail-config.yaml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: app-logs
    static_configs:
      - targets:
          - localhost
        labels:
          service: payment-api
          __path__: /var/log/app/*.log
```

The Promtail image above still runs, but treat it as legacy-only for local testing.

{{< insight bookmark >}}
**Promtail is end-of-life — ship new deployments with Grafana Alloy.** Promtail entered LTS in February 2025 and reached end-of-life on **March 2, 2026**: no further updates, fixes, or support. Grafana Alloy is the official replacement for sending logs to Loki. Migrate an existing Promtail config with `alloy convert --source-format=promtail --output=config.alloy promtail-config.yaml` — the scrape semantics carry over; the config language changes.
{{< /insight >}}

{{< obs-mascot class="bard" quip="Every log line is a verse; every stack trace, a tragic ballad. I have arranged ten thousand gateway_timeout errors into a concept album. It pages at 2am. It is my finest work. On-call did not ask for a concept album." caption="Bawk Dylan, who swears the error rate has a rhythm if you'd just LISTEN." >}}
