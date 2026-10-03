---
title: "Structured Logging: Teaching Machines to Read"
date: 2026-10-01
draft: false
excerpt: "Logs were designed for humans grepping text files at 2am. Now they also have to feed query engines, correlation and anomaly detection. Here's what that changes about what you write, and which field names to use."
readtime: 8
tags: ["Logs", "OpenTelemetry", "Structured Logging", "AI", "Observability"]
---

A log line that only a human can read is a log line that only a human can use. These days that is half the job.

Logs were designed for humans. Someone grepping through a text file at 2am, looking for the line that explains what went wrong. That was the use case. The format, the verbosity and the structure were all optimised for that one scenario.

That scenario is no longer the main one. Most log lines are now read first by a machine: a query engine filtering millions of events, a backend jumping from a trace to its logs, an anomaly detector learning what normal looks like. None of those can grep. They need structure, and a schema they can rely on without guessing. Logs that don't provide it are doing only half the job.

This isn't about prettier log output. It's about whether your logs can take part in automated analysis at all: cross-service queries, correlation with traces and metrics, and anomaly detection.

If you want the wider picture first — what logs are for, where they go and what belongs in them — start with [Logging Foundations](/guides/logging-foundations/).

## The Difference a Machine Cares About

Unstructured logging looks like this:

```
2026-05-14 14:32:01 ERROR Payment failed for order #12345 - insufficient funds
```

A human can read it instantly. A machine has to parse it, and that parsing is fragile. It breaks when the format changes slightly, when another service words the same failure differently, or when a field is added or removed. You can't reliably query across services that each express the same concept their own way.

Structured logging looks like this:

```json
{
  "timestamp": "2026-05-14T14:32:01Z",
  "severity_text": "ERROR",
  "event.name": "payment.failed",
  "service.name": "checkout-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "order.id": "ord_12345",
  "error.type": "insufficient_funds",
  "customer.tier": "standard",
  "duration_ms": 43
}
```

Every field can be queried. Every field is consistent across services that follow the same schema. A log backend, a correlation engine or a model can ingest this without any parsing logic. You can ask "show me all payment failures for premium customers in the last hour across every checkout service" and get an answer in milliseconds. You can't write that query against the first format, at least not reliably and not at scale.

## The Fields That Do the Real Work

Not every field carries equal weight. The ones that make logs machine-readable fall into three groups. If any group is missing, your logs are working at a fraction of their potential.

**Correlation fields.** `trace_id` and `span_id` connect a log event to the trace it belongs to. In OpenTelemetry's log data model they aren't attributes at all: `TraceId` and `SpanId` are fields of the log record itself. For logs written as JSON, OpenTelemetry's [non-OTLP trace context spec](https://opentelemetry.io/docs/specs/otel/compatibility/logging_trace_context/) fixes the names as top-level `trace_id`, `span_id` and `trace_flags`, in lowercase hex. With them, your backend can go from a metric spike to the relevant traces to the log lines that explain what happened, in one click. Without them, logs and traces live in separate worlds and correlation is manual work. A `request_id` can still be a useful application field, but it doesn't replace `trace_id`. Nothing outside your own code knows how to follow it.

**Event classification.** A stable event name such as `payment.failed` gives automated systems a shared vocabulary for what happened. It means the same thing whether it comes from the checkout service, the retry worker or the fraud pipeline. OpenTelemetry's log data model has a dedicated `EventName` field for exactly this. If your pipeline doesn't carry it yet, an `event.name` attribute with the same values does the job. Pair it with an outcome where one isn't obvious from the name. Without consistent names, every query, alert and detector has to learn each service's private wording, and in practice that never happens.

**Business context.** Fields like `customer.tier`, `order.id` or a feature-flag variant connect technical events to business outcomes. They let you ask "which customer segments are most affected by this degradation?" without joining logs against a separate database. They also make logs useful beyond incident response, for usage analysis and funnel debugging. They are also where personal data creeps in: use a pseudonymous reference rather than an email or user ID, as covered in [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/).

## Borrow Names Before You Invent Them

The quickest way to a schema that five teams will share is not to design one. OpenTelemetry's semantic conventions already name most of what a log line needs to say. Every backend that understands OpenTelemetry knows those names, so using them means your dashboards and queries carry across services and tools:

| You want to record | Use | Not |
|---|---|---|
| Which service emitted it | `service.name` (a resource attribute) | `service`, `app`, `svc_name` |
| Which version is running | `service.version` | `version`, `build` |
| Which environment | `deployment.environment.name` | `env`, `stage` |
| What went wrong, as a class | `error.type` | `error_code`, `errType` |
| The exception itself | `exception.type`, `exception.message`, `exception.stacktrace` | `ex`, `err_msg` |
| The HTTP route and status | `http.route`, `http.response.status_code` | `path`, `status` |

Your own fields follow the same style: lowercase, dot-namespaced by what they describe (`order.id`, `customer.tier`, `payment.provider`). Pick one style and hold every service to it. Consistency is what turns a pile of JSON into something you can query.

## Where Logs Finally Join the Pipeline

The OpenTelemetry log data model is stable, but the language SDKs are not equally far along. At the time of writing, the [OpenTelemetry status page](https://opentelemetry.io/status/) lists logs as stable in .NET and Java, a release candidate in Go, and still in development in Python and JavaScript. Traces are wired up everywhere and metrics are close behind. Logs are the signal most teams are still catching up on.

The key thing OpenTelemetry brings to logging isn't the format; JSON logs predate it by a decade. It's the **correlation bridge**. When logs go through the OTel SDK, or through a logging integration on top of it, the active trace context is attached to every record automatically. That single change is what makes cross-signal correlation work without manual field mapping.

If you're still shipping logs through a separate pipeline from your traces, fix that first. The Collector reads JSON, syslog and plain files, and its OTLP exporter puts them in the same pipeline as your traces and metrics. One caveat: a log line scraped from a file only correlates if the trace ID is already in the line *and* the Collector is told where to find it. [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) covers both halves for .NET, Java, Go and Python.

## What Becomes Possible

The case for structured logging isn't abstract. Here's what schema-consistent logs unlock that unstructured logs never could.

{{< mermaid caption="Fig. — A trace_id turns a burn rate alert into a straight line to root cause; without it, the same alert forces a manual, uncertain search across services." >}}
flowchart TD
    A["Burn rate alert fires"] --> B["Metric spike<br/>(error rate)"]
    B --> C["Correlated trace<br/>(via trace_id)"]
    C --> D["Exact log lines<br/>from that span"]
    D --> E["Root cause<br/>identified"]

    A2["Burn rate alert fires"] --> B2["Metric spike<br/>(error rate)"]
    B2 --> C2["Manual time search<br/>across services"]
    C2 -.-> D2["Maybe the right logs?<br/>(timestamp guess)"]
    D2 -.-> E2["Root cause<br/>possibly identified"]
{{< /mermaid >}}

**Correlation at incident time.** When a [burn rate alert](/howtos/set-up-slo-burn-rate-alerts/) fires, the ideal workflow is alert → trace → the log lines that explain the root cause. This chain only works if your logs carry `trace_id`. With it, the system does the correlation an engineer used to do by hand with timestamps. That is where most of the time goes in an investigation without it.

**Trend analysis across releases.** With a stable event name and `service.version` on every line, you can ask "did the rate of `payment.failed` change after the last deploy?" and get an answer from a single query. Without structure, someone first has to write a parser for each service's log format, and that work usually never gets done.

**Automated anomaly detection.** A model can learn what normal looks like for a service: which events fire, how often, and with what mix of outcomes. It can then flag a shift before it shows up in a dashboard. That only works with consistent event names; a detector that has to cluster free text first is guessing. The same is true of AI-assisted triage. It can reason over well-structured context, but there is little it can do with a wall of text.

## Where to Begin (Without Ripping Everything Up)

If you're instrumenting a new service, log through your language's OpenTelemetry integration from the start, with semantic-convention names and trace context attached. That's the baseline, and from scratch it costs very little extra.

If you're retrofitting existing services, start by adding `trace_id` and an event name to the log lines you already have, before reworking the whole schema. Correlation comes first. The rest of the schema can follow one service at a time.

And remember that consistency across services matters more than completeness within one. A shared schema that five teams follow is worth more than one team's perfect schema that nobody else matches. Settle on the field names and [log levels](/guides/log-levels-and-severity/) once, and write them down where every team will see them.

Your logs have been patient. Give them a schema they can work with.

{{< insight bookmark >}}
**The benchmark worth targeting.**
For any log event, you should be able to answer three questions without leaving your log query. What happened (the event name and its outcome)? Which request caused it (`trace_id`)? Who was affected (a pseudonymous customer reference and tier)? If any of the three needs a separate lookup, your schema has a gap worth closing. For a worked example of the third, see [Enrich Logs with Business Context in .NET](/howtos/enrich-logs-with-business-context-dotnet/).
{{< /insight >}}

{{< obs-mascot class="bard" quip="Behold my ballad: error. One word. A masterpiece. ...the machine cannot parse my masterpiece. Fine — level=error, service=checkout, order_id=4471. It does not rhyme. The parser wept with joy regardless." >}}
