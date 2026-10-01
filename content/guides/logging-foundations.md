---
title: "Logging Foundations"
date: 2026-10-01
draft: false
excerpt: "What logging is for, how it fits next to metrics and traces, and what to log, where and how. The mental model to have before touching a logging framework, and the starting point for the rest of the logging guides."
readtime: 9
tags: ["Logs", "Observability", "OpenTelemetry"]
---

Without a disciplined logging foundation, your observability stack is a collection of dashboards that can't explain anything. Metrics tell you something is wrong. Traces show you where. Logs tell you why — but only if you've captured the right context at the right moments. Most teams don't. They end up grepping through walls of unstructured text at 2am, reconstructing what happened from output that was never designed to be queried.

This guide is the mental model. The guides it links to at the end cover each part in depth.

## Logs Are the Connective Tissue, Not Just the Debug Stream

OpenTelemetry names the signals: traces, metrics and logs, with profiles joining them as a newer, still-maturing fourth. Logs carry something the others can't, which is the narrative of a single occurrence. A metric tells you the error rate spiked at 10:03. A log tells you which customer, which order and which downstream call failed, and why it failed at the application level. That difference matters when you're trying to connect a symptom to its cause across service boundaries.

Each signal covers ground the others can't. Logs don't replace metrics or traces; they make them actionable.

1. **Logs and metrics**
   - Logs: one record per occurrence, rich in context, expensive to store at volume
   - Metrics: numbers aggregated over time, cheap to store, blind to individual causes
   - Together: a metric tells you the error rate spiked at 10:03; the logs from that window tell you why

2. **Logs and traces**
   - Logs: what happened at a step, including values and outcomes
   - Traces: the shape of a request as it moves across services, with timing
   - Together: a trace shows which span was slow; the logs carrying that span's ID show what it was doing

3. **Logs and events**
   - Events: something specific happened, such as an order placed or a deploy finished
   - In OpenTelemetry an event *is* a log record, one with a name that says what kind of event it is
   - Together: a stable event name turns a stream of log lines into something you can count, compare across releases and alert on

4. **Logs and state**
   - Logs: a record of each transition, what changed and from what to what
   - Configuration and state stores: where the system is now, with no history of how it got there
   - Together: state shows where the system is; logs show the sequence of changes that got it there

5. **Logs and business data**
   - Logs: the technical event, such as which order, which payment and which failure
   - Business records (transactions, revenue): what that event meant to the business
   - Together: joined on a shared ID, "payment gateway returned an error" becomes "this outage cost $4,200 in failed premium-tier checkouts"

## Logging Philosophy

### Context Is What Separates a Log From a Line of Text

A log entry without context answers nothing. "Payment failed" tells you a failure occurred. It doesn't tell you which user, which payment method, which downstream dependency, or whether this was the first failure or the third retry. Every log should carry enough context to be read on its own and still say what happened and to whom, without a lookup in another system.

### The Maturity Progression: From Noise to Signal

Most teams start at level 1 and stay there longer than they should. Moving up isn't about adding more logs. It's about adding the right fields at the right moments. The difference between levels 1 and 3 isn't volume. At level 3 you can answer "which trace does this belong to, and who was affected?" without a manual investigation.

#### Level 1: Text With a Timestamp

Free text, read by people, searched with grep. Fine for one process on one host; useless across twenty services.

```json
{
  "timestamp": "2026-05-21T10:00:00Z",
  "level": "ERROR",
  "message": "Payment failed"
}
```

#### Level 2: Structured Fields

The same event, with the facts pulled out of the sentence into fields you can filter and group by. This is where queries like "all payment failures for provider X in the last hour" become possible.

```json
{
  "timestamp": "2026-05-21T10:00:00Z",
  "severity_text": "ERROR",
  "message": "Payment failed",
  "order.id": "ord_12345",
  "order.amount": 99.99,
  "payment.method": "card",
  "error.type": "gateway_timeout"
}
```

#### Level 3: Correlated and Shared

The fields follow names every service agrees on, the event has a name, and the trace context links it to the request that caused it. Business context is there too, carried as a pseudonymous reference rather than personal data.

```json
{
  "timestamp": "2026-05-21T10:00:00Z",
  "severity_text": "ERROR",
  "severity_number": 17,
  "service.name": "payment-api",
  "service.version": "2.14.0",
  "deployment.environment.name": "production",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b9c7c989f97918e1",
  "event.name": "payment.failed",
  "message": "Payment failed after 2 retries",
  "order.id": "ord_12345",
  "order.amount": 99.99,
  "payment.method": "card",
  "payment.retry_count": 2,
  "error.type": "gateway_timeout",
  "customer.tier": "premium",
  "customer.ref": "36bb095813943f38"
}
```

[Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/) explains each of these field choices, and which names to borrow from OpenTelemetry instead of inventing.

## What Logs Are For, Beyond Debugging

A well-structured log stream is also a record of what your system did on behalf of its users. Teams that treat logs as debug-only output leave value on the table. Teams that treat logs as the answer to everything end up with a log bill that grows faster than their traffic. Know what logs are good for, and what they're not:

- **Incident response and support.** A support ticket plus the matching log trail turns "the user says it broke" into "here's exactly what broke, for this user, at this time." This is the job logs do best.
- **Explaining performance.** A metric says the p99 got worse. The logs and spans from slow requests say which code path or dependency made them slow.
- **Product questions, in a pinch.** The event stream can answer "how often does anyone use the export button?" But if product analytics matters, give it its own event pipeline with its own schema and consent rules, rather than mining operational logs.
- **Compliance, with care.** Application logs aren't an audit trail. An audit trail has to be complete, tamper-evident and kept for a defined period; application logs are sampled, dropped under pressure and rotated. Keep the two separate, as [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) explains. The compliance question application logs *do* raise is the opposite one: what [personal data](/guides/pii-in-telemetry/) they're carrying that they shouldn't.

## Where Logs Go After You Write Them

Logs don't deliver value sitting in a file on one host. They need to flow through a collection layer, get enriched, cleaned and correlated, and land somewhere you can query them alongside traces and metrics.

{{< mermaid caption="Fig. — A log line leaves the application through the logging library and its OpenTelemetry bridge, is parsed, enriched, redacted and sampled in the Collector, and lands in a backend where it can be queried next to the traces and metrics from the same request." >}}
flowchart LR
    A[Application<br/>logging library] --> B[OTel bridge<br/>or file / stdout]
    B --> C[Collector<br/>parse, enrich,<br/>redact, sample]
    C --> D[Backend<br/>logs, traces, metrics]
    D --> E[Query and<br/>investigation]
    D --> F[Alerts on<br/>derived metrics]
{{< /mermaid >}}

### Key Integration Points

- **Collection.** Ship every host's and container's logs into one pipeline. Logs sent through an OpenTelemetry bridge carry the trace context with them. Logs scraped from files only correlate if the trace ID is in the line and the Collector knows where to find it; [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) covers both.
- **Processing and enrichment.** Parse unstructured lines into fields, and add context the application couldn't know, such as the Kubernetes pod, node or cloud region. This is also the last safe place to [mask sensitive data](/guides/data-masking-in-telemetry/) before it is stored anywhere.
- **Sampling and volume.** Sample the high-volume, low-value paths rather than storing every line at full fidelity, and keep the logging call itself off the request path; see [High-Throughput Logging: Sampling, Collectors, and the Wire](/guides/high-throughput-log-pipelines/).
- **Storage and retention.** Keep what you search during incidents searchable straight away, and decide retention per level and per data class rather than once for everything; [Log Levels](/guides/log-levels-and-severity/#cost-route-by-how-long-youll-need-it) shows one way to split it.
- **Alerting.** Alert on metrics derived from logs (an error *rate*, not individual lines), and better still on SLOs; use the logs to explain the alert rather than to raise it.

## Log at the Point of Consequence, Not at Every Entry and Exit

The most common logging mistake is wrapping every function in entry and exit logs. That gives you volume without coverage: a trail of execution, and nothing about the state that actually mattered. Tracing already records entry, exit and timing, with structure a stream of log lines loses. Log at the point of consequence instead: when a payment moves from pending to failed, when a retry limit is hit, when a circuit breaker opens. Log decisions and outcomes, not footsteps.

### What, How and When

1. **What to log**
   - Business events: the things a product manager would recognise, such as an order placed, a subscription cancelled or a payment retried
   - State changes: a resource moving from one state to another, not the fact that a function was called
   - Decisions under failure: anything that made the code choose (retry, fallback, give up), not just anything that returned an error code
   - Not measurements: latency, queue depth and memory belong in metrics, where they can be graphed and alerted on; a log line can *quote* a number that explains a decision

2. **How to log**
   - Use a structured format; free text collapses under any serious query load
   - Attach what the code knows (order, customer reference, outcome) when you emit the line; let the pipeline add what only it knows (pod, region, version)
   - Use the [message template, not string building](/qa/structured-logging-antipatterns/), so the values arrive as fields rather than baked into a sentence
   - Follow OpenTelemetry semantic conventions for field names, and keep personal data out

3. **When to log**
   - At meaningful points: state changes, decisions, failures
   - At the [level](/guides/log-levels-and-severity/) that reflects what the reader should do about it
   - With enough detail that the line is actionable without a follow-up investigation
   - With an eye on cost; debug-level logging at production throughput adds up fast

Good logs are an investment in your own future incident response. The fields you skip today are the ones you'll wish you had at 2am next month. Start structured, keep the context close to the event, and tie every log to the trace it belongs to.

## Where to Go Next

- [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/): the schema, and which field names to use
- [Log Levels: When to Whisper, Speak, or Shout](/guides/log-levels-and-severity/): choosing the level for each event, and what each one costs
- [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/): connecting each log line to its trace, in .NET, Java, Go and Python
- [Enrich Logs with Business Context in .NET](/howtos/enrich-logs-with-business-context-dotnet/): adding who-was-affected fields without leaking personal data
- [High-Throughput Logging: Keeping the Hot Path Fast](/guides/high-throughput-logging/): when the logging call itself becomes the bottleneck

{{< obs-mascot class="bard" quip="Sing, O Cucco, of the NullPointerException — of the stack trace that launched a thousand pages, and the lone engineer who grepped it at dawn." >}}
