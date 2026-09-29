---
title: "The Dashboard Was Green. The Request Was Broken."
date: 2026-09-27
draft: false
excerpt: "Metrics tell you something is wrong. Logs tell you what happened in one place. Distributed tracing tells you what the request actually went through, and that's a different question entirely."
readtime: 6
tags: ["Tracing", "Observability", "OpenTelemetry", "Sampling", "Debugging"]
---

The alert fires at 2am. You pull up the dashboard. Error rate: 0.3%, within normal bounds. Latency p50: 42ms, healthy. Service health checks: green across the board. You spend twenty minutes convincing yourself it's a false alarm, until a second engineer joins the call and pastes a user complaint into Slack. Checkout is broken. Not for everyone. Just for users with a promotional discount code on a cart that contains one particular product category.

Your metrics had no idea.

Finding the root cause took another forty minutes of manual log correlation across four services. A distributed trace would have taken thirty seconds: follow the spans, find the database call that returned a null discount object, and watch that null flow downstream as a $0.00 total with no error raised anywhere.

This isn't an edge case. It's the default failure mode of metric-first observability, applied to systems that were never monolithic.

## The Three Witnesses

Think of your observability stack as three different kinds of witness at an incident scene.

Logs are eyewitnesses. They're detailed, specific and local, and they tell you exactly what happened inside one service at one moment. The trouble is that each one only saw its own corner of the room. Cross-examining five log streams to rebuild what happened to one request across five services is detective work, and detective work is slow at 2am.

Metrics are statistics. They tell you how often things happen, how fast, and in what total. You need them for capacity planning, SLO tracking and spotting trends. They're close to useless for "why did *this specific request* fail?", because metrics throw away the individual case on purpose, in favour of the population.

Traces are the surveillance tape. They follow one request from the moment it enters your system to the moment a response goes back, recording every service boundary it crossed, every database query it triggered and every millisecond it spent waiting. The unit is the request, not the event and not the aggregate. That's a fundamentally different question.

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
    API-->>U: 200 OK, checkout "succeeded"
{{< /mermaid >}}

## How DORA Made This Worse

In 2018, the founders of the DevOps Research and Assessment group published *Accelerate*, one of the most influential engineering books of the decade. It gave the industry something it badly needed: a shared vocabulary for delivery performance. Its four metrics (deployment frequency, lead time for changes, change failure rate and mean time to restore) became the shorthand for engineering excellence. DORA has refined and renamed them since, but the idea stuck. The research holds up, and the framework was exactly the right tool for the job it was built for.

The side effect was subtler. Once something as complex as software delivery gets boiled down to four numbers, an industry learns to expect that the right dashboard answers any question. The reflex became automatic: when something goes wrong, find the metric that captures it. Build the dashboard. Watch the number.

Here's the category error. DORA metrics measure the outcome of your delivery *process*. They describe how well your organisation ships software over time. They aren't diagnostic tools for a single failed request. Mean time to restore tells you your average restore last quarter took 47 minutes. It tells you nothing about *why* tonight's incident took an hour: which service was the culprit, which team owned it, which code path failed, which upstream dependency quietly returned nothing.

That hour is where distributed tracing lives. Your delivery metrics can tell you restores are getting slower. Only the trace tells you where this one started.

## Why Tracing Didn't Win Sooner

Distributed tracing has existed since Google published the [Dapper paper](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/) in 2010. Twitter open-sourced Zipkin in 2012, and Uber open-sourced Jaeger in 2017. If the value was always there, why did mainstream adoption take another decade?

Two barriers, mostly.

The first was instrumentation fragmentation. Tracing meant picking a vendor (Zipkin, Jaeger, Lightstep, Datadog) and adding that vendor's SDK to every service in your call graph. Instrumentation was sticky, expensive and a migration nightmare. OpenTracing and OpenCensus tried to fix that, but two competing standards is its own kind of fragmentation, and they didn't merge into OpenTelemetry until 2019. Teams with fifty services faced a real cost-benefit calculation, and plenty decided the friction wasn't worth it.

The second was the sampling trap. At 100% capture, distributed tracing is expensive. Store every span from every request in a busy system and your storage bill grows with every request you serve. The standard answer was head-based sampling: flip a coin at the entry point, trace 5 to 10% of requests, and analyse the sample.

The problem is that head-based sampling is blind. It throws traces away before it knows whether they're interesting. The slow requests, the errors and the odd code paths all get sampled at the same rate as the boring, successful majority. You end up with a representative sample that's mostly the traces you don't need.

## What Changed

OpenTelemetry fixed the fragmentation. One API and specification, with an SDK for each language, works across backends, and the W3C Trace Context standard (the `traceparent` header) means spans propagate correctly without vendor middleware. Auto-instrumentation agents (bytecode-level for Java, monkey-patching for Python and Node.js) instrument existing services without code changes. The lock-in that made tracing expensive a few years ago is largely gone.

Tail-based sampling fixed the sampling trap. Instead of deciding at the start of a trace, the OpenTelemetry Collector's `tail_sampling` processor buffers spans and decides later. It can't know when a trace has really finished, so it waits a fixed `decision_wait` after a trace's first span arrives and decides then. Spans that arrive after that miss the decision, so set `decision_wait` longer than your slowest normal request. Within that window, you can keep every trace that contains an error, every trace over a latency threshold, and a light sample of the rest:

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

The traces you actually want, the anomalous ones, no longer get thrown away at random. The boring successful traffic gets sampled lightly for statistical coverage.

{{< insight >}}
**Tail sampling uses OR semantics.** A trace is kept if *any* policy samples it, and policy order doesn't set priority. At scale, with several Collector replicas, run a first tier of Collectors with the `loadbalancingexporter` in front of the sampling tier, so every span of a trace reaches the same replica. Tail sampling needs the whole trace in one place to decide correctly. Without that routing, a trace split across replicas gets judged on half its spans.
{{< /insight >}}

## Where to Start

The instrumentation gap is the right place to begin, and it's smaller than it used to be.

Add the OTel SDK to one service: the entry point for your most critical user flow. Keep the default W3C propagator and configure an OTLP exporter. If the next service downstream already has OTel instrumentation or a framework-level auto-instrumentation agent, the spans will chain on their own. Now you've got a two-node trace, and that's already useful. Extend the instrumented path one service at a time until the critical call chain is covered.

Four signals pay for themselves straight away: `http.request.method`, `http.response.status_code`, `db.query.text` (sanitised), and a span status of Error with `error.type` set on failures. With those, you can filter to every failed trace, every slow database call and every error, without hand-correlating log files across services.

What DORA's numbers can't show you isn't on any dashboard. It's in the trace that shows exactly which service and which call turned a three-minute fix into an hour-long incident. Your dashboard will still be green. At least now you'll know what to reach for when that's not the whole story.
