---
title: "The Power of Structured Events"
date: 2026-06-07
draft: true
excerpt: "Metrics aggregate. Logs describe. Traces follow. But structured events can do all three — and they are the foundation of truly observable systems."
readtime: 6
tags: ["Observability", "Logs", "Philosophy"]
---

The industry decided early on to split observability data into three categories: logs, metrics, and traces. This was a tooling decision, not a conceptual one. The three pillars model emerged because different tools were built for each signal type, and we organised our thinking around the tools we had.

The underlying reality is simpler. There is one primitive: the structured event.

## What a Structured Event Actually Is

A structured event is a key-value record — something happened, here is the context around it.

```json
{
  "timestamp": "2026-06-10T14:32:01.847Z",
  "service.name": "checkout-api",
  "event": "payment.processed",
  "order.id": "ord-9f2a8c",
  "payment.amount": 142.50,
  "payment.currency": "GBP",
  "payment.provider": "stripe",
  "payment.duration_ms": 234,
  "user.tier": "premium",
  "http.status_code": 200,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

This is a log. It is also a trace span. It is also the raw material for a metric. The category depends entirely on what you do with it downstream — not what it is.

## How the Three Pillars Emerge from One Primitive

**Traces** are structured events correlated by a shared identifier. The `trace_id` field above links this event to every other event in the same request chain. Add a `parent_span_id` and you have a parent-child relationship. Collect all events sharing a trace ID and you have a distributed trace. The trace is not a different data type — it is a view over structured events with a specific correlation attribute.

**Metrics** are structured events aggregated over time. Take ten thousand `payment.processed` events from the last minute, count them, and you have a request rate. Take their `payment.duration_ms` values and compute the p95, and you have a latency histogram. The metric does not exist in the event itself — it is produced by aggregating events. A metric is a lossy compression of structured events: faster to query, cheaper to store, but stripped of the individual context that made debugging possible.

**Logs** — in the traditional sense of unstructured text — are structured events that failed to be structured. A log line like `INFO: payment processed for user 4821 in 234ms` contains the same information as the JSON above, but encoded for human reading, not machine querying. The shift to structured logging is the shift from text output to structured events.

## Why the Distinction Matters

If all three signals come from the same primitive, two things follow.

**You do not need three separate instrumentation systems.** The same call that creates a span can emit the event as a log. The same event that is sampled into a trace can be aggregated into a metric. OpenTelemetry is built on this principle — one SDK, one pipeline, one Collector — because the signals are fundamentally the same data at different levels of aggregation and correlation.

**The richness of your telemetry is determined at emission time, not at query time.** Once you emit an unstructured log line, you cannot retroactively add the `order.id` that would let you filter by order. Once you aggregate events into a metric, you cannot recover the individual events that produced it. The attributes you include — or exclude — when the event is emitted define the ceiling of your analytical power permanently.

## The Attribute Is the Unit of Observability Value

The event is the container. The attribute is what gives it value.

A span with `duration_ms: 234` tells you one request was slow. A span with `duration_ms: 234, user.tier: "premium", payment.provider: "stripe", order.id: "ord-9f2a8c"` tells you *which* request was slow, *who* it affected, *which* provider was involved, and *which* specific order you can look up. That context is the difference between knowing something is wrong and understanding why.

The cost of attributes is cardinality when they become metric labels, and storage when they ride on every event. Both costs are real. But the cost of not having the attribute during an incident is always higher.

## What Comprehensive Instrumentation Means in Practice

A system is comprehensively instrumented when every operation that matters — a request boundary, an external call, a state transition, an error — emits a structured event with enough attributes to answer "what happened here and why" without additional context.

Not every line of code. Not every function call. The signal-to-noise ratio matters as much as completeness. The goal is coverage of the decision points your system makes, not a record of its entire execution.

The heuristic: instrument everywhere a request can succeed or fail for a different reason. An HTTP handler. A database query. A payment provider call. A cache miss that triggers a fallback. These are the events that, when something goes wrong, you will wish you had.

- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — turning the "logs that failed to be structured" case above into real structured events
- [OTel Semantic Conventions](/guides/otel-semantic-conventions/) — the shared attribute vocabulary that makes structured events queryable across services
- [Cardinality Management](/guides/cardinality-management/) — what happens when the attributes that make events valuable also become metric labels

<!-- TODO: Add section on Honeycomb-style wide events vs narrow spans — the tradeoff -->
<!-- TODO: Add section on how OTel bridges the three pillars into one pipeline -->
