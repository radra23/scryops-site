---
title: "Logging Foundations"
date: 2026-06-07
draft: true
excerpt: "What logging actually is, why it matters beyond debugging, and how it fits into the broader observability stack — the mental model every engineer should have before touching a logging framework."
readtime: 7
tags: ["Logs", "Observability", "OpenTelemetry"]
---

Without a disciplined logging foundation, your observability stack is a collection of dashboards that can't explain anything. Metrics tell you something is wrong. Traces show you where. Logs tell you why — but only if you've captured the right context at the right moments. Most teams don't. They end up grep-ing through walls of unstructured text at 2am, reconstructing what happened from output that was never designed to be queried.

## Logs Are the Connective Tissue, Not Just the Debug Stream

Logs sit alongside metrics, traces, and state data in the observability stack, but they carry something the others can't: event-level narrative. A metric tells you that error rate spiked at 10:03. A log tells you which customer, which order, which downstream call failed, and why it failed at the application level. That distinction matters when you're trying to correlate a symptom to a cause across service boundaries.

{{< mermaid caption="Fig. — Observability data splits into five types: event, time series, request, state, and business. Logs are one branch under event data, not the whole picture." >}}
graph TD
    A[Observability] --> B[Event Data]
    A --> C[Time Series Data]
    A --> D[Request Data]
    A --> E[State Data]
    A --> F[Business Data]
    
    B --> B1[Logs]
    B --> B2[Events]
    B --> B3[Audit Trails]
    
    C --> C1[Metrics]
    C --> C2[Counters]
    C --> C3[Gauges]
    
    D --> D1[Traces]
    D --> D2[Profiles]
    D --> D3[Flows]
    
    E --> E1[Configurations]
    E --> E2[Deployments]
    E --> E3[Resources]
    
    F --> F1[Transactions]
    F --> F2[User Actions]
    F --> F3[Business Metrics]
    
    style A fill:#1C1C1C,stroke:#D4820A,color:#F5A623,stroke-width:2.5px,stroke-dasharray:5 3
    style B fill:#161616,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
    style C fill:#161616,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
    style D fill:#161616,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
    style E fill:#161616,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
    style F fill:#161616,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
{{< /mermaid >}}

Each signal type covers ground the others can't. Logs don't replace metrics or traces — they make them actionable.

1. **Logs and Event Data**
   - Logs — narrate what happened and why, with full context attached to a single occurrence
   - Events — mark that something specific occurred, often without the surrounding narrative
   - Together — a log gives an event its "why," turning a bare occurrence into an explained one

2. **Logs and Time Series Data**
   - Logs — one record per occurrence, rich in context, expensive to store at volume
   - Metrics — aggregated numbers over time, cheap to store, blind to individual causes
   - Together — a metric tells you error rate spiked at 10:03; the logs from that window tell you why

3. **Logs and Request Data**
   - Logs — what happened at each step, including values and outcomes
   - Traces — the shape of a request as it moves across services, with timing
   - Together — a trace shows which span was slow; the log attached to that span shows what it was doing

4. **Logs and State Data**
   - Logs — a record of the transition: what changed, from what, to what
   - Configuration and state stores — the system's current state, with no history of how it got there
   - Together — state data shows where the system is now; logs show the sequence of transitions that got it there

5. **Logs and Business Data**
   - Logs — the technical event: which order, which payment, which failure
   - Business data (transactions, revenue records) — the business meaning of that event
   - Together — connecting the two turns "payment gateway returned an error" into "this outage cost $4,200 in failed premium-tier checkouts"

## Logging Philosophy

### Context Is What Separates a Log From a Line of Text

An uncontextualized log entry answers nothing. "Payment failed" tells you a failure occurred. It doesn't tell you which user, which payment method, which downstream dependency, or whether this is the first failure or the third retry. Every log must carry enough context that it can be read in isolation — without cross-referencing a separate system — and still convey what happened and to whom.

### The Maturity Progression: From Noise to Signal

Most teams start at Level 1 and stay there longer than they should. Moving up the progression isn't about adding more logs — it's about adding the right fields at the right moments. The difference between Level 1 and Level 3 is not volume; it's the ability to answer "what was the business impact and which trace does this belong to?" without a manual investigation.

#### Level 1: Basic Logging
- Simple text logs
- Basic error logging
- Manual log analysis
- Limited context

```json
{
  "timestamp": "2024-03-21T10:00:00Z",
  "level": "ERROR",
  "message": "Payment failed"
}
```

#### Level 2: Enhanced Logging
- Structured logging
- Contextual information
- Basic correlation
- Automated analysis

```json
{
  "timestamp": "2024-03-21T10:00:00Z",
  "level": "ERROR",
  "message": "Payment failed",
  "context": {
    "order_id": "12345",
    "amount": 99.99,
    "payment_method": "credit_card"
  },
  "error": {
    "type": "PaymentGatewayError",
    "code": "PG_001"
  }
}
```

#### Level 3: Advanced Logging
- Full observability integration
- Cross-service correlation
- Business context
- Predictive analysis

```json
{
  "timestamp": "2024-03-21T10:00:00Z",
  "level": "ERROR",
  "message": "Payment failed",
  "context": {
    "order_id": "12345",
    "amount": 99.99,
    "payment_method": "credit_card",
    "customer_tier": "premium",
    "business_unit": "ecommerce"
  },
  "error": {
    "type": "PaymentGatewayError",
    "code": "PG_001",
    "retry_count": 2
  },
  "observability": {
    "trace_id": "0af7651916cd43dd8448eb211c80319c",
    "span_id": "b9c7c989f97918e1",
    "service": "payment-api",
    "environment": "production"
  },
  "business_impact": {
    "affected_customers": 1,
    "revenue_impact": 99.99,
    "sla_breach": false
  }
}
```

## Logs Carry Business Value That Metrics Can't

Logging is not just an operational tool. A well-structured log stream is also a record of what your system did on behalf of users — which makes it the primary source of truth for compliance, audit, and business analysis. Teams that treat logs as debug-only output leave that value on the floor.

### Beyond Debugging

- **Business intelligence** — which features get used, in what sequence, by which customer segment. The same event stream that helps you debug also answers what your product actually does in the field.
- **Compliance and audit** — a queryable record of who accessed what and when, which is exactly what auditors and regulators ask for after the fact, not before.
- **Performance optimization** — logs pinpoint which specific code path or dependency is slow, where a metric only tells you that something got slower.
- **Customer experience** — a support ticket plus the matching log trail turns "the user says it broke" into "here's exactly what broke, for this user, at this timestamp."

## Integration with Observability Stack

Logs don't deliver value sitting in a file on a single host. They need to flow through a collection layer, get enriched and correlated, and land somewhere queryable. The architecture below shows how logs connect to the broader observability platform — and where correlation with traces and metrics happens.

{{< mermaid caption="Fig. — Logs and the other signal types flow from the application through a shared collection and enrichment layer before reaching the platform, where they feed analysis, alerting, and business intelligence." >}}
graph LR
    A[Application] --> B[Event Data]
    A --> C[Time Series Data]
    A --> D[Request Data]
    A --> E[State Data]
    A --> F[Business Data]
    
    B --> G[Data Collection]
    C --> G
    D --> G
    E --> G
    F --> G
    
    G --> H[Observability Platform]
    
    H --> I[Analysis & Visualization]
    H --> J[Alerting]
    H --> K[Business Intelligence]
    
    style A fill:#1C1C1C,stroke:#D4820A,color:#F5A623,stroke-width:2.5px,stroke-dasharray:5 3
    style H fill:#161616,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
{{< /mermaid >}}

### Key Integration Points

- **Data collection** — aggregate from every host and container into one pipeline, propagate trace and request context along with the log line, and sample the high-volume, low-value paths rather than storing every entry at full fidelity.
- **Processing and enrichment** — parse unstructured lines into fields, attach context that wasn't available at emission time (service version, deployment ID), and correlate entries that belong to the same request or trace.
- **Storage and retention** — hot storage for what's actively queried, cold storage for what's kept for compliance, and a retention schedule tied to how long each data class is actually useful.
- **Analysis and visualization** — full-text and field-level search, pattern detection across large volumes, and dashboards that turn raw entries into business-readable signal.

## Log at the Point of Consequence, Not at Every Entry and Exit

The most common logging mistake is wrapping every function in entry/exit logs. This produces volume without coverage — you get a trail of execution, but nothing about the state that actually matters. Log at the point of state change: when a payment transitions from pending to failed, when a retry limit is hit, when a circuit breaker trips. Log decisions and outcomes, not footsteps.

### What to Log

1. **What to Log**
   - Business events — the things a product manager would recognize: an order placed, a subscription cancelled, a payment retried
   - State changes — a resource moving from one state to another, not the fact that a function was called
   - Error conditions — anything that required a decision (retry, fallback, give up), not just anything that returned non-200
   - Performance data — the numbers you'd actually reach for during an incident: latency, queue depth, retry counts

2. **How to Log**
   - Use structured format — free-text logs collapse under any serious query load
   - Include context at emission time, not during post-hoc enrichment
   - Follow standards (OpenTelemetry Semantic Conventions for field names)
   - Consider sampling for high-volume, low-value paths

3. **When to Log**
   - At meaningful points — state changes, decisions, failures
   - With the severity level that reflects actual impact
   - With enough detail that the log is actionable without a follow-up investigation
   - With awareness of cost — debug-level logs in production at high throughput add up fast

Good logs are an investment in your own future incident response. The fields you skip today are the fields you'll wish existed at 2am next month. Start structured, keep context close to the event, and tie every log to the trace it belongs to.

- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — how to move from free-text to queryable, structured output
- [Log Levels: When to Whisper, Speak, or Shout](/guides/log-levels-and-severity/) — choosing the right verbosity for each event
- [Wiring Trace IDs into Logs](/howtos/wire-trace-ids-into-logs/) — connecting logs to the distributed trace they belong to

{{< obs-mascot class="bard" quip="Sing, O Cucco, of the NullPointerException — of the stack trace that launched a thousand pages, and the lone engineer who grepped it at dawn." >}}
