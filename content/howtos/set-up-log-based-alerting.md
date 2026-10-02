---
title: "Set Up Log-Based Alerting with Loki and Grafana"
date: 2026-06-10
draft: false
excerpt: "Turn a LogQL query into a Grafana-managed alert rule that fires on error volume, a specific error type or a failing dependency. Covers the query, the rule settings that trip people up, routing to PagerDuty and Slack, and an end-to-end test."
readtime: 8
tags: ["Logs", "Observability", "Alerting", "Grafana", "How-to"]
---

Metrics alert on rates. Logs alert on specifics. If you need to fire when one error type shows up more than N times a minute, or when one dependency starts failing, and no metric exists for it, the log stream is what you have.

The result is a Grafana-managed alert rule backed by a LogQL query, routed to PagerDuty or Slack by a `severity` label, with a notification that carries a runbook link. [Log-Based Monitoring](/guides/log-based-monitoring/) is the conceptual companion: why these queries work, and when a log-derived metric is the better choice.

{{< mermaid caption="Fig. — Logs arrive in Loki over OTLP. A Grafana alert rule evaluates a LogQL query, and the notification policy routes on the rule's severity label." >}}
flowchart LR
    app["Service<br/>(OTel SDK)"] -->|OTLP| loki[("Loki")]
    loki --> rule["Alert rule<br/>LogQL + threshold"]
    rule --> policy["Notification<br/>policy"]
    policy -->|critical| pd["PagerDuty"]
    policy -->|warning| slack["Slack"]
{{< /mermaid >}}

## What you'll need

- Loki 3.x receiving logs over OTLP at its `/otlp` endpoint, and Grafana with Loki added as a data source. The [quickstart at the end](#docker-compose-quickstart) gives you both locally.
- Structured logs with OpenTelemetry field names: `service.name` as a resource attribute, a numeric severity, and `error.type` on failures. [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/) covers the schema.

Loki promotes `service.name` to the index label `service_name`. Severity, trace IDs and log attributes land as structured metadata, with dots turned into underscores (`error.type` becomes `error_type`), so you filter on them without a parser. If you ship JSON lines instead of OTLP, add `| json` after the stream selector and the same field names come out.

## Step 1 — Confirm the Logs Are There

Open Grafana → **Explore**, pick the Loki data source and run:

```logql
{service_name="payment-api"}
```

No results means nothing is arriving under that name. Check the exporter's endpoint and that the service sets `service.name` at startup. A service that never sets it lands under an `unknown_service` name instead.

Expand any line. The detail panel lists the structured metadata, and you want to see `severity_number`, `error_type` and `trace_id` there. If `severity_number` is missing, the logging bridge isn't mapping levels. Alert rules filter on that number, so fix it before going further. [Log Levels](/guides/log-levels-and-severity/#one-scale-many-dialects) has the mapping: 17 and above is ERROR.

## Step 2 — Write the Detection Query

Pick the pattern that matches your failure.

**Error volume:**

```logql
sum(count_over_time({service_name="payment-api"} | severity_number >= 17 [1m]))
```

Error records per minute across every instance of `payment-api`. Filtering on the number catches `Error`, `ERROR` and `err` alike.

**A specific error type:**

```logql
sum(count_over_time({service_name="payment-api"} | error_type="gateway_timeout" [5m]))
```

One `gateway_timeout` may deserve a page where a hundred `validation_error` records don't. Swap in any bounded field from your schema.

**A failing dependency:**

```logql
sum(count_over_time({service_name="checkout"} | upstream_service="inventory" | severity_number >= 17 [5m]))
```

This fires when inventory is failing, not when anything in checkout misbehaves, so checkout's on-call isn't chasing a problem that belongs to another team.

Leave the comparison (`> 5`) out of the query. The threshold goes in the rule, and Step 3 explains why that matters. Run each query in Explore over the last few hours first, to see what the normal level looks like before you pick a number.

*Queries checked against the Loki LogQL docs and Loki's OTLP ingestion source (v3.7); not run against a live Loki.*

## Step 3 — Create the Alert Rule

Go to **Alerts & IRM → Alert rules → + New alert rule**.

**Query and condition.** Select the Loki data source and paste the query. Set the query **Type** to **Instant**. A range query returns many points per series, and the rule can only compare one number. Instant gives you that number without a separate Reduce step. Then set the alert condition to **Is above 5**. For an error type you never expect to see, **Is above 0** is fine.

**No data handling.** This is the setting most log alerts get wrong. A LogQL metric query returns *no series* when no lines match, not a `0`. For an error count, no matching lines is the healthy case. Left on the default, a quiet service sends the rule to the No Data state instead of resolving. Under **Configure no data and error handling**, set the no-data state to **Normal**.

**Evaluation.** Choose a folder and an evaluation group with a `1m` interval. Set the **pending period** to `2m`, so the condition has to hold across consecutive evaluations before the alert fires. That absorbs one-off spikes. For a failure where a single occurrence matters, set it to `0s`.

**Labels.** Add `severity=critical` or `severity=warning`, plus `service=payment-api`. The notification policy routes on these, so they are not cosmetic. [Alert Severity Levels](/guides/alert-severity-levels/) covers which failures earn which level.

**Annotations.** Fill in **Summary** and **Runbook URL**. Template the summary from the query's own value:

```text
payment-api logged {{ $values.A.Value }} error records in the last minute
```

`$values` holds the result of each instant query and expression by its Ref ID. The query is `A` unless you renamed it. Grafana's docs recommend it over `$value`, which renders every query and expression as one long string. [Alert Design Principles](/articles/alert-design-principles/#the-four-questions-every-alert-must-answer) covers what else belongs in the body.

**Notifications.** Route through the notification policy tree rather than picking a single contact point. Routing by label is what Step 4 sets up. Save the rule.

*Checked against Grafana's alert rule, Loki alerting and template reference docs; not run.*

## Step 4 — Route to PagerDuty and Slack

Create two contact points under **Alerts & IRM → Alerting → Contact points**.

**PagerDuty.** In PagerDuty, add an **Events API V2** integration to the service and copy its integration key. In Grafana, pick the PagerDuty integration and paste the key. The **Severity** field is optional and defaults to `critical`. It accepts a template, such as `{{ .CommonLabels.severity }}`, and must resolve to `critical`, `error`, `warning` or `info`. Anything else falls back to `critical`. Grafana can't set incident priority (P1, P2). Configure that on the PagerDuty side.

**Slack.** Paste an incoming-webhook URL (`https://hooks.slack.com/services/...`), or use a bot token with a channel ID as the recipient. Either way, one contact point posts to one channel. Under the optional settings, template the title and text body:

```text
{{ .CommonLabels.service }}: {{ .CommonAnnotations.summary }}
```

```text
{{ range .Alerts.Firing }}{{ .Annotations.summary }}
Runbook: {{ .Annotations.runbook_url }}
{{ end }}
```

`$values` and `$labels` belong to the rule's annotations. Notification templates see different data: the grouped alerts, each with its own `.Labels` and `.Annotations`. That's why the body loops over `.Alerts.Firing`.

Then open **Notification policies** and add two child policies under the default policy:

- matcher `severity = critical` → PagerDuty contact point
- matcher `severity = warning` → Slack contact point

Anything that matches neither falls through to the default policy's contact point. Labels are what make the page deliberate rather than universal.

*Checked against Grafana's PagerDuty, Slack and notification template docs and the PagerDuty receiver source; not run.*

## Step 5 — Test It End to End

Push error records straight into Loki's OTLP endpoint. This loop sends one every two seconds for three minutes, enough to clear a threshold of 5 per minute for longer than the 2-minute pending period:

```bash
for i in $(seq 1 90); do
  ts="$(date +%s)000000000"   # nanoseconds; macOS date has no %N
  curl -s -X POST http://localhost:3100/otlp/v1/logs \
    -H "Content-Type: application/json" \
    -d '{"resourceLogs":[{"resource":{"attributes":[
          {"key":"service.name","value":{"stringValue":"payment-api"}}]},
        "scopeLogs":[{"logRecords":[{
          "timeUnixNano":"'"$ts"'",
          "severityNumber":17,"severityText":"ERROR",
          "body":{"stringValue":"payment failed: gateway timeout ('"$i"')"},
          "attributes":[{"key":"error.type","value":{"stringValue":"gateway_timeout"}}]
        }]}]}]}'
  sleep 2
done
```

*Payload checked against the OTLP/JSON encoding and Loki's `/otlp/v1/logs` handler; the generated JSON was validated, the `curl` was not run.*

On the rule list, watch the state move from **Normal** to **Pending** (condition met, pending period running) to **Firing**. If it stays Normal, open the rule's state history and run the query in Explore over the same window. Then check the data source with **Connections → Data sources → Loki → Save & test**. This is a Grafana-managed rule, so it evaluates in Grafana and the Loki ruler plays no part.

Once it fires, check the notification. The summary should show the count and the runbook link should resolve. Then stop the loop and confirm the alert resolves rather than going to No Data. That's the no-data setting from Step 3 doing its job.

The push proves the alert pipeline, not your service. Before you rely on the rule, trigger the real failure path once, in staging, so you know the service writes the record the query expects.

## Adapting the Query

**Group by bounded fields only.** Filtering on a `user_id` or `request_id` is fine for an investigation. Grouping an alert by one isn't. `sum by (user_id)` creates a series, and potentially an alert, per user. Group by something with a handful of values instead:

```logql
sum by (error_type) (
  count_over_time({service_name="payment-api"} | severity_number >= 17 [5m])
)
```

Each `error_type` becomes its own alert instance, with the value in `$labels.error_type`. [Cardinality: Aggregate First](/guides/log-based-monitoring/#cardinality-aggregate-first-alert-on-the-aggregate) explains the stream-level side of the same trap.

**Alert on a ratio when traffic varies.** A fixed count misfires both ways when volume swings. Divide by total requests instead:

```logql
sum(count_over_time({service_name="checkout"} | http_response_status_code >= 500 [5m]))
/
sum(count_over_time({service_name="checkout"} | http_response_status_code != "" [5m]))
```

Set the rule's condition to **Is above 0.05**. This only works when each request writes exactly one record carrying `http.response.status_code`. Count every line and the denominator measures chattiness, not traffic. A ratio like this is also an SLI. Fed into multi-window burn-rate alerts, a 14.4× burn on a 30-day SLO exhausts the budget in about 2.1 days. [SLOs and Error Budgets](/guides/slos-and-error-budgets/#burn-rate-alerts) has the math, and [How to Set Up Your First SLO and Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) the rules.

**Correlate services in one rule.** Add a second query (`B`) to the same rule, for example inventory's 503 count, and replace the threshold with a Math expression such as `$A > 0 && $B > 5`. Both queries need to be instant, or reduced, for that. The rule fires only when both conditions hold. [Multi-Condition Alerts](/guides/log-based-monitoring/#multi-condition-alerts) covers when that is worth the complexity.

## Docker Compose Quickstart

Loki and Grafana locally, with Loki already provisioned as a data source. Loki's image ships a config with structured metadata enabled and the `/otlp` endpoint on by default, so it needs no config file of its own. Anonymous admin access is for a laptop only.

```yaml
# docker-compose.yaml
services:
  loki:
    image: grafana/loki:3.7.8
    ports:
      - "3100:3100"

  grafana:
    image: grafana/grafana:13.2.3
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    volumes:
      - ./loki-datasource.yaml:/etc/grafana/provisioning/datasources/loki.yaml:ro
    depends_on:
      - loki
```

```yaml
# loki-datasource.yaml
apiVersion: 1
datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
```

Point your service's OTLP log exporter, or an OpenTelemetry Collector's `otlphttp` exporter, at `http://localhost:3100/otlp`. The exporter appends `/v1/logs` itself. Or use the test loop from Step 5 as your traffic.

*Checked against the Loki v3.7.8 image's bundled config and Grafana's provisioning docs; YAML validated; not run.*

{{< insight bookmark >}}
**Still on Promtail? It reached end-of-life on March 2, 2026** and gets no further fixes. Grafana Alloy is the replacement for shipping logs to Loki. `alloy convert --source-format=promtail --output=config.alloy promtail-config.yaml` translates an existing config. The scrape semantics carry over and the config language changes. New services can skip the shipper entirely and send OTLP, as above.
{{< /insight >}}

{{< obs-mascot class="bard" quip="Every log line is a verse; every stack trace, a tragic ballad. I have arranged ten thousand gateway_timeout errors into a concept album. It pages at 2am. It is my finest work. On-call did not ask for a concept album." caption="Bawk Dylan, who swears the error rate has a rhythm if you'd just LISTEN." >}}
