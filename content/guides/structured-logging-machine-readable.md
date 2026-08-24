---
title: "Structured Logging: Teaching Machines to Read"
date: 2026-05-26
draft: true
excerpt: "Logs were designed for humans grepping text files at 2am. In 2026, they need to work for ML models and correlation engines too. Here's what that means for what you write."
readtime: 8
tags: ["Logs", "OpenTelemetry", "Structured Logging", "AI", "Observability"]
---

A log line that only a human can read is a log line that only a human can use. In 2026, that's half the job.

Logs were designed for humans. Someone grepping through a text file at 2am, looking for the line that explains what went wrong. That was the use case. The format, the verbosity, the structure: all of it was optimised for that one scenario.

That scenario is no longer the primary one.

In 2026, the most valuable thing your logs can do is feed a system that processes millions of events per second, correlates across services and signals, and surfaces patterns a human would never find manually. That system can't grep. It needs structure. It needs a consistent schema it can parse without guessing. And if your logs aren't providing that, they're only doing half the job.

This isn't about prettier log output. It's about whether your telemetry can participate in automated analysis, ML-based anomaly detection, and the kind of cross-signal correlation that turns reactive incident response into something closer to prediction.

## The Difference a Machine Cares About

Unstructured logging looks like this:

```
2026-05-14 14:32:01 ERROR Payment failed for order #12345 - insufficient funds
```

A human can read it instantly. A machine has to parse it — and that parsing is fragile. It breaks when the format changes slightly, when a different service uses different wording, when a field gets added or removed. You can't reliably query across services that each express the same concept differently.

Structured logging looks like this:

```json
{
  "timestamp": "2026-05-14T14:32:01Z",
  "level": "error",
  "event_type": "payment_failed",
  "service": "checkout-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "order_id": "order_12345",
  "error_code": "insufficient_funds",
  "customer_tier": "standard",
  "duration_ms": 43
}
```

Every field is queryable. Every field is consistent across services that follow the same schema. A log aggregation system, a correlation engine, or an ML model can ingest this without any parsing logic. You can ask "show me all payment failures for premium customers in the last hour across all checkout services" and get an answer in milliseconds. That's not a query you could write against the first format — not reliably, and not at scale.

## The Fields That Do the Real Work

Not every field in a log entry carries equal weight. The ones that unlock machine-readable analysis fall into three categories — and if any of them are missing, your logs are working at a fraction of their potential.

**Correlation fields.** `trace_id` and `span_id` are what connect a log event to the trace it belongs to — these are standardised OTel semantic convention fields. Without them, logs and traces live in separate worlds, and correlation is a manual task. With them, your observability platform can jump from a metric spike to the relevant traces to the log lines that explain what happened — in a single click. Use the exact names the OpenTelemetry spec defines, and use them consistently across every service. A `request_id` can be a useful custom field, but it is not part of the OTel correlation model — use it for application-layer correlation, not as a substitute for `trace_id`.

**Event classification.** `event_type` and `event_outcome` (success, failure, partial) give automated systems a consistent vocabulary for what happened. "payment_failed" means the same thing whether it comes from the checkout service, the retry worker, or the fraud detection pipeline. Without consistent classification, pattern detection has to learn each service's unique naming conventions — and that rarely happens.

**Business context.** `customer_tier`, `order_value`, `feature_flag` — the fields that connect technical events to business outcomes. These are what let you ask "which customer segments are most affected by this degradation?" without joining logs against a separate database. They're also what makes logs useful beyond incident response, for things like usage analysis and funnel debugging.

## Where Logs Finally Join the Pipeline

OpenTelemetry's logs signal reached stability in 2024, and adoption has been accelerating since — but logs remain the least mature of the three signals in most production environments. Traces are wired up everywhere. Metrics are close behind. Logs are still catching up.

The key change OTel brings to logging isn't the format — JSON structured logs predate OTel by a decade. It's the **correlation bridge**: when you emit logs through the OTel SDK, the current trace context (trace ID, span ID) is automatically attached to every log record. That single change is what makes cross-signal correlation work without manual field mapping.

If you're still shipping logs through a separate pipeline from your traces, that's the first thing to fix. The OTel Collector's log receivers handle most common formats — JSON, syslog, file-based — and the OTLP log exporter gets them into the same pipeline as your traces and metrics. The wiring is one afternoon's work. The payoff is the rest of your incidents.

## What Becomes Possible

The case for structured logging isn't abstract. Here's what schema-consistent logs actually unlock that unstructured logs never could.

{{< mermaid caption="Fig. — A trace_id turns a burn rate alert into a straight line to root cause; without it, the same alert forces a manual, uncertain search across services." >}}
flowchart LR
    A["🔔 Burn rate alert fires"] --> B["📊 Metric spike<br/>(error rate)"]
    B --> C["🔍 Correlated trace<br/>(via trace_id)"]
    C --> D["📋 Exact log lines<br/>from that span"]
    D --> E["✅ Root cause<br/>identified"]

    A2["🔔 Burn rate alert fires"] --> B2["📊 Metric spike<br/>(error rate)"]
    B2 --> C2["🕐 Manual time search<br/>across services"]
    C2 --> D2["📋 Maybe the right logs?<br/>(timestamp guess)"]
    D2 --> E2["❓ Root cause<br/>possibly identified"]

    style A fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style E fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style A2 fill:#2A1A0A,stroke:#D4820A,color:#F5A623,stroke-width:2.5px,stroke-dasharray:5 3
    style E2 fill:#2A1A0A,stroke:#D4820A,color:#F5A623,stroke-width:2.5px,stroke-dasharray:5 3
{{< /mermaid >}}

**Automated anomaly detection.** ML models can learn what "normal" log patterns look like for a service — which event types fire, at what rates, with what distribution of outcomes — and flag deviations before they manifest as metric changes. This requires consistent `event_type` classification. An AI-assisted triage tool can reason over well-structured context; it can do nothing useful with wall-of-text log lines.

**Correlation at incident time.** When a burn rate alert fires, the ideal workflow is: alert → trace → log lines explaining the root cause. This chain only works if your logs carry `trace_id`. Teams with correlated telemetry consistently report faster MTTR and root cause analysis — not because they're better engineers, but because the system performs the correlation that used to be manual. The mechanics of injecting trace context into your log output are covered in [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/).

**Trend analysis across releases.** With structured logs, you can ask "did the error rate for this `event_type` change after the last deploy?" and get an answer automatically. Without structure, someone has to write a custom parser for each service's log format first — and that work usually doesn't happen.

## Where to Begin (Without Ripping Everything Up)

If you're instrumenting a new service, use the OTel logging SDK from the start and emit JSON with trace context attached. That's the baseline, and it's not much extra work when you're building from scratch.

If you're retrofitting structured logging onto existing services, the most impactful first step is adding `trace_id` and `event_type` to your existing log lines before reworking the entire schema. Correlation comes first. Schema completeness can follow iteratively, service by service.

And remember: consistency across services matters more than completeness within a single service. A shared logging schema that five teams follow is more valuable than one team's perfectly detailed schema that nobody else matches.

Your logs have been patient. Give them a schema they can work with.

{{< insight bookmark >}}
**The benchmark worth targeting.**
For any log event, you should be able to answer three questions without leaving your log query: What happened (`event_type` + outcome)? Which request caused it (`trace_id`)? Who was affected (customer context)? If any of those three require a separate lookup, your schema has a gap worth closing.
{{< /insight >}}

{{< obs-mascot class="bard" quip="Behold my ballad: error. One word. A masterpiece. ...the machine cannot parse my masterpiece. Fine — level=error, service=checkout, order_id=4471. It does not rhyme. The parser wept with joy regardless." >}}
