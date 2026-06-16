---
title: "The Dashboard Was Green. The Request Was Broken."
date: 2026-06-16
draft: false
excerpt: "Metrics tell you something is wrong. Logs tell you what happened at one specific place. Distributed tracing tells you what the request actually experienced — and that's a different question entirely."
readtime: 6
tags: ["Tracing", "Observability", "OpenTelemetry", "Sampling", "Debugging"]
---

> "The metric was flat. The trace was screaming. We were watching the wrong thing."
> — Anonymous

The alert fires at 2am. You pull up the dashboard. Error rate: 0.3%, within normal bounds. Latency p50: 42ms, healthy. Service health checks: green across the board. You spend twenty minutes convincing yourself this is a false alarm — until a second engineer joins the call and pastes a user complaint into Slack. Checkout is broken. Not for everyone. For users with a promotional discount code applied to a cart containing a specific product category.

Your metrics had no idea.

Finding the root cause took forty minutes of manual log correlation across four services. A distributed trace would have taken thirty seconds: follow the span, find the database call that returned a null discount object, see the exception that swallowed the error silently downstream.

This is not an edge case. It is the default failure mode of metric-first observability applied to systems that were never monolithic.

## The Three Witnesses

Think of your observability stack as three different kinds of witness at an incident scene.

Logs are eyewitnesses — detailed, specific, and local. They tell you exactly what happened inside one service at one moment in time. The problem is they only saw one corner of the room. Cross-examining five log streams to reconstruct what happened to one request across five services is detective work, and detective work is slow at 2am.

Metrics are statistics. They tell you how often things are happening, how fast, at what aggregate. They are essential for capacity planning, SLO tracking, and spotting trends. They are nearly useless for answering "why did *this specific request* fail?" — because metrics, by design, throw away the individual case in favour of the population.

Traces are the surveillance tape. They follow a single request from the moment it enters your system to the moment a response returns, recording every service boundary it crossed, every database query it triggered, every millisecond it waited. The unit of measure is the request, not the event, not the aggregate. That is a fundamentally different question.

{{< mermaid >}}
sequenceDiagram
    participant U as User
    participant API as API Gateway
    participant Cart as Cart Service
    participant Promo as Promo Service
    participant DB as Orders DB

    U->>API: POST /checkout (trace-id: a1b2c3)
    API->>Cart: validate cart (span: cart.validate)
    Cart->>Promo: apply discount (span: promo.apply)
    Promo->>DB: SELECT discount WHERE code=... (span: db.query 847ms ⚠)
    DB-->>Promo: null
    Promo-->>Cart: discount: null (no error thrown)
    Cart-->>API: total: $0.00
    API-->>U: 200 OK — checkout "succeeded"
{{< /mermaid >}}

## How DORA Made This Worse

In 2018, the DevOps Research and Assessment group published *Accelerate* — one of the most influential engineering books of the decade. It gave the industry something it badly needed: a shared vocabulary for delivery performance. Four metrics — deployment frequency, lead time for changes, change failure rate, and mean time to restore — became the shorthand for engineering excellence. The research holds up, and the framework was exactly the right tool for the job it was designed for.

The unintended side effect was subtler. When something as complex as software delivery gets successfully reduced to four numbers, it trains an industry to expect that the right dashboard answers any question. The instinct became reflexive: when something goes wrong, find the metric that captures it. Build the dashboard. Watch the number.

The category error is this: DORA metrics are outcome measures for your delivery *process*. They describe how well your organisation ships software over time. They are not diagnostic tools for individual request failures. "Mean time to restore" tells you your MTTR was 47 minutes last quarter. It tells you nothing about *why* this incident took 47 minutes — which service was the culprit, which team owned it, which code path failed, which upstream dependency timed out without surfacing an error.

That 47-minute gap is where distributed tracing lives. Metrics told you the fire happened. Tracing tells you where it started.

## Why Tracing Didn't Win Sooner

Distributed tracing has existed since Google published the Dapper paper in 2010. Zipkin shipped in 2012. Jaeger in 2016. If the value was always there, why did mainstream adoption take another decade?

Two barriers, mostly.

The first was instrumentation fragmentation. Before OpenTelemetry, instrumenting for tracing meant choosing a vendor — Zipkin, Jaeger, Lightstep, Datadog — and adding that vendor's SDK to every service in your call graph. Instrumentation was sticky, expensive, and a migration nightmare. Teams with fifty services faced a genuine cost-benefit calculation, and many decided the friction outweighed the benefit.

The second was the sampling trap. At 100% capture, distributed tracing is expensive. Store every span from every request in a high-volume system and you will outspend your engineering salary budget on storage. The standard answer was head-based sampling: flip a coin at the entry point, trace 5–10% of requests, analyse the sample.

The problem is that head-based sampling is blind. It discards traces before it knows whether they are interesting. The slow requests, the errors, the anomalous code paths — all sampled at the same probability as the boring, successful majority. You end up with a representative sample of exactly the traces you don't need.

## What Changed

OpenTelemetry resolved the fragmentation problem. A single SDK with a stable API works across backends, and the W3C Trace Context standard (`traceparent` header) means spans propagate correctly without vendor middleware. Auto-instrumentation agents — bytecode-level for Java, monkey-patch for Python and Node.js — instrument existing services without code changes. The lock-in that made tracing adoption expensive before 2020 is largely gone.

Tail-based sampling resolved the sampling trap. Instead of making a keep/discard decision at the start of a trace, the OpenTelemetry Collector's `tail_sampling` processor buffers all spans and makes the decision *after* the trace completes. You can keep 100% of traces containing an error, 100% that exceed a latency threshold, and sample the normal remainder at a low rate:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow-traces
        type: latency
        latency: {threshold_ms: 1000}
      - name: baseline-sample
        type: probabilistic
        probabilistic: {sampling_percentage: 5}
```

The traces you actually want — the anomalous ones — are no longer randomly discarded. The boring successful traffic is sampled lightly for statistical coverage.

{{< insight >}}
**Tail sampling uses OR semantics.** A trace is kept if *any* policy returns sampled — policy order does not determine priority. At scale with multiple Collector replicas, pair tail sampling with the `loadbalancingexporter` to route all spans for the same trace-ID to the same replica. Tail sampling requires the complete trace in one place to make a correct keep/discard decision; without affinity routing, a trace split across replicas will be evaluated on incomplete data.
{{< /insight >}}

## Where to Start

The instrumentation gap is the right place to begin, and it is smaller than it used to be.

Add the OTel SDK to one service — the entry point for your most critical user flow. Configure it to emit spans with `traceparent` propagation enabled. If the downstream service already has OTel instrumentation or a framework-level auto-instrumentation agent, spans will chain automatically. You now have a two-node trace. That is already useful. Extend the instrumented path one service at a time until the critical call chain is covered.

Four span attributes that pay for themselves immediately: `http.method`, `http.status_code`, `db.statement` (sanitised), and `error`. With these you can filter to all failed traces, all slow database calls, and all errors — without manually correlating log files across services.

The metric that DORA forgot is not in any dashboard. It is in the trace that shows you exactly which service, which call, and which line of code turned a three-minute incident into a forty-seven minute one. Your dashboard will still be green. At least now you'll know what to reach for when that's not the whole story.
