---
title: "Log-Based Monitoring: Alerting on the Evidence"
date: 2026-06-10
draft: false
excerpt: "Logs carry operational state at a resolution metrics can't match. Most teams only open them after something breaks. This guide covers how to query them continuously, turn them into metrics, and alert on what they surface without blowing up cardinality or cost."
readtime: 11
tags: ["Logs", "Observability", "Alerting", "Structured Logging"]
---

A metric tells you a rate changed. A log tells you which request failed, on which endpoint, with which error, after which dependency returned a 503. Metrics are the summary; logs are the evidence. Log-based monitoring means treating that evidence as a continuous operational signal, not an archive you open after something goes wrong.

## Forensics Is Not Monitoring

Most teams use logs in one mode: forensics. An alert fires, someone opens the log browser, and the searching starts. That's a valid use. It isn't monitoring.

Monitoring means long-lived queries evaluated on a schedule, with thresholds and alert rules attached. The tool doesn't decide which mode you're in. Grafana, Kibana and CloudWatch all do both. What decides it is whether your log queries exist as rules or only as one-off searches someone types at 2am.

The architecture is the same one metric alerting uses: a data source, a query layer and an alert rule. The difference is that logs resist aggregation. Free text, inconsistent field names and missing fields all break the query layer, unless structure is enforced where the log is written.

A quick test: could you answer "how many payment requests failed between 02:00 and 02:05, broken down by failure type" from your logs alone, in one query? If not, you have forensics, not monitoring.

## Prerequisite: Fields You Can Count On

Free-text logs support exactly one monitoring pattern: string matching. You can alert when a line contains "connection refused". You can't group by error type, compute a rate per service, or derive a latency percentile.

Everything below assumes structured records with stable field names. Stable means the same name carries the same meaning in every service, every time. [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/#borrow-names-before-you-invent-them) covers which names to use, and they're OpenTelemetry's semantic conventions rather than anything invented here. For monitoring, the ones that matter most are:

- **Severity**, as OpenTelemetry's numeric `SeverityNumber`. Alert on the number, not the text. `severity_number >= 17` catches every error whether the service wrote `Error`, `ERROR` or `err`. [Log Levels: When to Whisper, Speak, or Shout](/guides/log-levels-and-severity/#one-scale-many-dialects) has the full mapping.
- **`service.name`**, set once at startup as a resource attribute, never computed per call.
- **`error.type`** on every failure, as a short stable class (`gateway_timeout`, `rate_limited`), not buried in the message.
- **`trace_id`**, so a log-based alert can jump straight to the trace. [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) covers the plumbing.

Here's the difference in practice:

```text
# Free text: string matching only
2026-06-10 14:22:01 ERROR Failed to process payment for order 12345: gateway timeout

# Structured: every field is queryable, groupable, alertable
{"timestamp":"2026-06-10T14:22:01Z","severity_text":"ERROR","severity_number":17,"service.name":"payment-api","event.name":"payment.failed","error.type":"gateway_timeout","payment.provider":"stripe","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","duration_ms":5003}
```

The first line tells a human what happened. The second tells a query engine. None of the patterns below work on the first. If your services disagree on names or types today, [Common Logging Pitfalls](/guides/common-logging-pitfalls/) is the place to start.

## Query Patterns

The examples use LogQL against Loki, with logs arriving over OTLP. That path matters for the syntax. Loki promotes a short list of resource attributes, `service.name` among them, to index labels with dots turned into underscores (`service_name`). Log attributes, severity and trace IDs land as [structured metadata](https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/), so you filter on them directly with no parser. If you ship JSON lines instead, add `| json` after the selector. Loki sanitises the extracted keys the same way, so `error.type` becomes `error_type` either way. (Checked against the Loki docs, not run against a live Loki.)

### Counts and Ratios

The basic query counts matching records over a rolling window, grouped by a field:

```logql
# Errors per minute, per service
sum by (service_name) (
  count_over_time({service_name=~".+"} | severity_number >= 17 [1m])
)
```

Raw counts catch volume spikes, and they mislead whenever traffic varies. Fifty errors a minute is an outage at 1,000 requests a minute and noise at 100,000. Alert on a ratio instead:

```logql
# Share of requests answered with a 5xx, over 5 minutes
sum(count_over_time({service_name="checkout"} | http_response_status_code >= 500 [5m]))
/
sum(count_over_time({service_name="checkout"} | http_response_status_code != "" [5m]))
```

This only works if each request produces exactly one record carrying `http.response.status_code`, an access-log style completion event. Count every line the service writes and the denominator measures chattiness, not traffic.

A ratio like this is also a perfectly good SLI. Feed it into multi-window burn-rate alerts, where a 14.4× burn on a 30-day SLO exhausts the budget in about 2.1 days, not hours. [SLOs and Error Budgets](/guides/slos-and-error-budgets/#burn-rate-alerts) has the math and [How to Set Up Your First SLO and Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) the rules.

### Narrow Failures Hide in Aggregates

Aggregate ratios miss failures that are narrowly scoped. If one payment provider fails every request and handles 0.1% of traffic, the service-wide error rate looks like a rounding error. For those customers, it's a complete outage. Field-level queries surface it:

```logql
# A specific failure class, broken out
sum by (error_type) (
  count_over_time({service_name="payment-api"} | severity_number >= 17 [5m])
) > 3

# A specific upstream returning 503s
count_over_time(
  {service_name="checkout"} | upstream_service="inventory" | http_response_status_code="503" [5m]
) > 0
```

Grouping by `error_type` is safe because it's bounded: a handful of values, set by your code. That distinction matters again in the cardinality section. The same logic applies to retry storms. Log each retry as its own event and count those, rather than trying to spot one request ID appearing many times.

### Latency from Logs

When there's no trace backend, a `duration_ms` attribute gives you latency. LogQL can compute quantiles over an unwrapped field:

```logql
quantile_over_time(0.95,
  {service_name="api-gateway"} | http_route != "" | unwrap duration_ms | __error__="" [5m]
) by (http_route)
```

The `__error__=""` filter drops records where `duration_ms` didn't convert to a number, instead of letting them fail the query. The caveat is sampling. This is p95 *of the records you kept*. If you keep every error but only 10% of successes, the sample is skewed towards failures, and so is the percentile. State how the logs were sampled whenever you quote a number like this.

### Baselines Instead of Fixed Thresholds

A fixed threshold works when the steady state is stable. Under variable load it fails both ways: set for peak, it misses failures at 3am; set for 3am, it fires every lunchtime. LogQL's `offset` modifier lets you compare against the same window last week:

```logql
sum(count_over_time({service_name="checkout"} | severity_number >= 17 [1h]))
>
3 * sum(count_over_time({service_name="checkout"} | severity_number >= 17 [1h] offset 1w))
```

The `offset` has to follow the range selector directly. Watch the zero case: if last week's window had no errors, any error at all trips it, so pair it with a small absolute floor. Loki has no built-in anomaly detection. Statistical baselines beyond this mean Grafana Cloud's machine-learning features or an external tool, and a ratio threshold evaluated over two windows covers most cases without either.

## Cardinality: Aggregate First, Alert on the Aggregate

User IDs, request IDs, trace IDs and session IDs are excellent log fields. They're terrible grouping keys.

In Loki, index labels define streams. Every unique label combination is a separate stream with its own index entry and chunks. Promote `user_id` to a label and you get a stream per user, which is the quickest way to make Loki slow and expensive. Loki's default OTLP mapping already keeps log attributes and trace IDs in structured metadata rather than the index. Resist the urge to promote them.

The same trap reappears one level up. `sum by (user_id) (...)` in an alert or recording rule creates one series, and potentially one alert, per user. Group by a bounded dimension instead (`error_type`, `customer_tier`, `region`). When you need the culprit, follow the alert into the logs and find it there. If those IDs identify people, [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) is worth reading before they go anywhere near a label.

## Log-to-Metric Derivation

Every alert evaluation re-reads and re-filters the raw logs in its window. For a rule evaluated every minute, that's a lot of repeated work for one number. Deriving a metric once and alerting on the metric is cheaper and faster. It's the right move for logs you inherit and can't re-instrument. For new code, emit the metric at the source.

**In Loki**, any metric query can become a recording rule. Data-source-managed recording rules run in the Loki ruler and remote-write their results to a Prometheus-compatible store. Grafana can also run Grafana-managed recording rules against Loki. Either way, the `sum by (error_type)` query above becomes a cheap series instead of a repeated scan.

**In the OpenTelemetry Collector**, the `count` connector turns log records into counts before they reach any backend. The config below was written for `otel/opentelemetry-collector-contrib` v0.158 or later and checked against the component READMEs, not run:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

connectors:
  count:
    logs:
      app.log.errors:
        description: Log records at ERROR severity or above
        conditions:
          - log.severity_number >= SEVERITY_NUMBER_ERROR
        attributes:
          - key: error.type
            default_value: unknown   # without this, errors missing the attribute aren't counted

processors:
  delta_to_cumulative: {}   # count emits delta sums; remote write drops them

exporters:
  otlphttp/loki:
    endpoint: http://loki:3100/otlp
  prometheusremotewrite:
    endpoint: http://prometheus:9090/api/v1/write

service:
  pipelines:
    logs:
      receivers: [otlp]
      exporters: [otlphttp/loki, count]
    metrics/from_logs:
      receivers: [count]
      processors: [delta_to_cumulative]
      exporters: [prometheusremotewrite]
```

Four details in that file are easy to get wrong:

- **Loki takes OTLP over HTTP**, at `/otlp`. Use the `otlphttp` exporter, which appends `/v1/logs` itself. The gRPC `otlp` exporter won't work here.
- **The count connector emits delta sums**, and the `prometheusremotewrite` exporter drops non-cumulative sums. Without `delta_to_cumulative`, the metric silently never arrives. (Before v0.158 the processor was called `deltatocumulative`, and that name still works as a deprecated alias.) Prometheus also needs `--web.enable-remote-write-receiver` to accept the write.
- **`default_value` matters.** A record without the attribute is skipped, so an error missing `error.type` would vanish from the very count meant to catch it.
- **Image choice.** The `count` connector and `delta_to_cumulative` processor ship in the contrib distribution, not the core `otel/opentelemetry-collector` image. The count connector is still alpha for logs.

## Alerting on Logs

Two engines can evaluate a LogQL alert. **Grafana-managed rules** run in Grafana and query Loki as a data source. **Data-source-managed rules** live in and run on the Loki ruler. Grafana's docs recommend Grafana-managed rules as the default. They support multiple queries per rule, expressions, no-data and error states, and alert state history. Pick the Loki ruler when you want rules versioned and evaluated alongside Loki itself, independent of Grafana, and accept the extra moving part.

### Multi-Condition Alerts

Single-signal alerts produce false positives. An error from the payment service warrants a look. An error from the payment service, plus 503s from inventory, starting within five minutes of a deploy, is an incident with a probable cause.

When all the conditions live on the same record, chain the filters as in the upstream-503 query above. When they come from different services, one Grafana-managed rule can hold several queries and combine them with a math expression such as `$A > 0 && $B > 5`. It fires only when both hold. For correlating alerts that are already firing across services, [Alert Correlation](/guides/alert-correlation/) covers topology- and time-based grouping.

Whatever fires still has to be worth waking up for. [Alert Design Principles](/articles/alert-design-principles/) covers what the alert body must say, and [Alert Severity Levels](/guides/alert-severity-levels/) covers who it should reach.

## Retention and Query Cost

Log monitoring wants two tiers with very different performance.

The **hot tier** serves alert evaluation and incident investigation, and must answer in seconds. Size it from your own investigations: if P1 reviews routinely look back 14 days, the hot tier is 14 days. The **cold tier** serves compliance, audits and slow post-mortems. Compressed object storage is fine, and so are queries that take minutes. Length is set by your retention obligations, not by monitoring.

The bigger lever is what you index and what you ingest at all. Vendor surveys keep finding cost overruns are common: Elastic's [2026 observability landscape report](https://www.elastic.co/resources/observability/report/landscape-observability-report) puts the share of respondents hitting unexpected costs at 67%, from a vendor-run survey of 500+ practitioners.

**Drop noise before ingestion.** The Collector's `filter` processor ships in both core and contrib images:

```yaml
processors:
  filter/drop_debug:
    error_mode: ignore
    log_conditions:
      - log.severity_number > SEVERITY_NUMBER_UNSPECIFIED and log.severity_number < SEVERITY_NUMBER_INFO
```

The first half of the condition is load-bearing. Records whose severity was never set have `severity_number` 0, and a bare `< SEVERITY_NUMBER_INFO` drops them too. That's often every line scraped from a file without a severity parser. (`log_conditions` arrived in contrib v0.146. Older configs use the now-deprecated `logs: log_record:` form.) [High-Throughput Logging](/guides/high-throughput-log-pipelines/) goes further into sampling and batching at the Collector.

**In Loki**, keep index labels to a few low-cardinality dimensions such as service, environment, region and namespace. Leave everything else in structured metadata or the line itself.

**In Elasticsearch and OpenSearch**, map monitoring fields explicitly. Dynamic mapping turns any JSON string into a `text` field with a `keyword` sub-field. So a status code that arrives as `"503"` compares as text, and `"503" < "6"` is true. Define an index template before the first document lands:

```json
{
  "index_patterns": ["logs-app-*"],
  "template": {
    "mappings": {
      "properties": {
        "@timestamp":     { "type": "date" },
        "severity_number": { "type": "byte" },
        "service.name":   { "type": "keyword" },
        "error.type":     { "type": "keyword" },
        "http.response.status_code": { "type": "short" },
        "trace_id":       { "type": "keyword" },
        "duration_ms":    { "type": "long" },
        "message":        { "type": "text" }
      }
    }
  }
}
```

That's the body of `PUT _index_template/logs-app` (checked against the Elasticsearch docs, JSON validated, not run against a cluster). Dotted names like `service.name` map as object paths, which is what OpenTelemetry-shaped documents expect. Move indices from hot to warm to cold with ILM in Elasticsearch, or ISM, its OpenSearch counterpart. Line the phases up with the tiers above. The type mismatch behind the `"503"` problem is [one of the common logging pitfalls](/guides/common-logging-pitfalls/) for a reason.

## CloudWatch Logs

CloudWatch gives you two alerting paths. **Metric filters** match events at ingest and publish a CloudWatch metric you can alarm on. Patterns understand JSON, as in `{ $.level = "error" }`, and can attach dimensions. Every distinct dimension value creates a new metric, so the cardinality rule applies here too. Filters only count events that arrive after they're created.

**Log alarms** evaluate a Logs Insights query directly, with no metric filter in between. CloudWatch runs the query as a scheduled query (`rate(5 minutes)`, say) and alarms when M of the last N results breach the threshold. A `by` clause in the aggregation expression evaluates each contributor separately, up to 500 per run. That's more expressive than a filter pattern, at the cost of latency set by the schedule. Logs Insights has its own pipe-based language, not SQL:

```text
fields @timestamp, status_code
| filter level = "error"
| stats count() as error_count by status_code
| sort error_count desc
```

Use metric filters for fast, simple signals and log alarms where minute-level delay is acceptable.

## What Log-Based Monitoring Doesn't Replace

**Infrastructure metrics.** CPU, memory, disk and network saturation come from the host or runtime, not your application's logs. No amount of logging reports a saturated NIC as reliably as the host does.

**Traces for latency attribution.** A log with `duration_ms` says a request took 450 ms. A trace says 380 ms of it was a database call. Log-derived latency is a stopgap until traces exist. After that, it's a less accurate copy.

Use logs for application-layer state: business events, error specifics, dependency failure modes and request-level context. Use metrics for infrastructure and high-volume SLIs, and traces for where the time went. [Distributed Logging](/guides/distributed-logging/) and [Log Context Enrichment](/guides/log-context-enrichment/) cover getting the right fields onto every record across services, which is what makes every query in this guide possible.
