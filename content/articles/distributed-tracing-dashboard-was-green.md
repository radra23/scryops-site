---
title: "The dashboard was green, but the request was broken."
date: 2026-09-27
draft: false
excerpt: "Metrics show something is wrong; logs report what happened in a specific place, but distributed tracing tells you what the request actually went through, and that's a different question entirely."
readtime: 6
tags: ["Tracing", "Observability", "OpenTelemetry", "Sampling", "Debugging"]
---

It’s 2 a.m., and your phone almost vibrates off the table. You stumble to your laptop, open the dashboard, and see a sea of green: error rate at 0.3%, latency p50 at 42ms, health checks all smiling. You start to think this is just another false alarm. Twenty minutes later, another engineer hops on and drops a user complaint into Slack. Turns out, checkout is broken—but only for folks using a promo code on a cart with one very specific product category. The plot thickens.

Your metrics had no idea.

You burn another forty minutes playing log detective, piecing clues from four different services. If you'd had a distributed trace, you could have solved it in thirty seconds: follow the spans, spot the database call that handed back a null discount, and watch it slip downstream like a mimic posing as a treasure chest, disguised as a perfectly respectable $0.00 total: no error, no alarm, just a silent fail waiting for someone to open the lid.

This isn’t some rare edge case. It’s the classic failure mode when you rely on metrics first, especially in systems that were never a tidy monolith to begin with.

{{< obs-green-dashboard-vs-trace >}}

## The Three Witnesses

Picture your observability stack as three types of witnesses at the scene of an incident.

Logs are your classic eyewitnesses: detailed, specific, and a bit myopic. Each one saw exactly what happened in its own little corner, but none of them caught the whole show. Trying to put together a single request from five different log streams is pure detective work—and let’s be honest, nobody wants to play Sherlock at 2am.

Metrics are the statisticians in the room. They’ll tell you how often things happen, how fast, and in what total. Perfect for capacity planning, SLOs, and trend-spotting. But if you want to know why *this* request failed, metrics shrug—they’re designed to toss out the individual stories and focus on the crowd.

Traces are your surveillance footage. They follow a single request from the front door to the exit, catching every service hop, every database query, and every millisecond spent twiddling its thumbs. Here, the star of the show is the request itself, more than an event, less than a summary. That’s a whole different way of asking questions.

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

In 2018, the founders of the DevOps Research and Assessment group published *Accelerate*, one of the most influential engineering books of the decade. It gave the industry something it badly needed: a shared vocabulary for delivery performance. Its four metrics (deployment frequency, lead time for changes, change failure rate, and mean time to restore) became the benchmark you'll measure every engineering team against. DORA has since refined and renamed them, but the idea stuck. The research holds up, and the framework was exactly the right tool for the job it was built for.

But there was a sneaky side effect. Once software delivery got boiled down to four tidy numbers, everyone started expecting the dashboard to have all the answers. The reflex kicked in: something’s wrong? Find the metric. Build the dashboard. Stare at the number.

Here’s where the wires get crossed. DORA metrics are all about your delivery process—they show how well your team ships software over time. They’re not built to diagnose a single failed request. Mean time to restore might tell you last quarter’s average was 47 minutes, but it won’t say a word about why tonight’s incident dragged on for an hour: which service tripped up, which team owned it, which code path went astray, or which upstream quietly ghosted you.

That mysterious hour? That’s distributed tracing’s home turf. Delivery metrics can tell you things are slowing down, but only a trace will show you exactly where this one began its journey to nowhere.

## Why Tracing Didn't Win Sooner

Distributed tracing has existed since Google published the [Dapper paper](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/) in 2010. Twitter open-sourced Zipkin in 2012, and Uber open-sourced Jaeger in 2017. If the value was always there, why did mainstream adoption take another decade?

There were really two big roadblocks.

First up: instrumentation fragmentation. Tracing used to mean picking a vendor—Zipkin, Jaeger, Lightstep, Datadog—and bolting their SDK onto every service in your call graph. It was sticky, pricey, and migrating later was a headache. OpenTracing and OpenCensus tried to help, but having two standards just meant double the confusion. They finally merged into OpenTelemetry in 2019. If you had fifty services, you had to do the math, and a lot of teams just decided it wasn’t worth the hassle.

Second: the sampling trap. Capturing every single trace is expensive—store every span from every request and your storage bill balloons with every user click. The usual fix was head-based sampling: flip a coin at the front door, trace 5 or 10% of requests, and hope the sample tells the story.

But head-based sampling is flying blind. It tosses traces before it knows if they’re interesting. The slow requests, the errors, the weird edge cases—they get sampled just as often as the boring, happy-path traffic. You end up with a sample that’s statistically fair, but mostly full of traces you’ll never care about.

{{< obs-head-vs-tail-sampling >}}

## What Changed

OpenTelemetry came along and fixed the fragmentation mess. Now there’s one API and spec, with an SDK for every language, and the W3C Trace Context standard (that’s the `traceparent` header) keeps spans passing smoothly without vendor lock-in. Auto-instrumentation agents—bytecode for Java, monkey-patching for Python and Node.js—let you instrument existing services without touching the code. The sticky vendor lock-in that made tracing a pain? That’s mostly history.

Tail-based sampling solved the sampling trap. Instead of making a snap decision at the start, the OpenTelemetry Collector’s `tail_sampling` processor buffers spans and waits. It doesn’t know exactly when a trace is done, so it waits a set `decision_wait` after the first span shows up, then makes the call. Any spans that arrive late miss the boat, so set `decision_wait` longer than your slowest normal request. Within that window, you can keep every trace with an error, every slowpoke over your latency threshold, and just a pinch of the rest:

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

Now, the traces you actually care about, like the weird, there'll be dragons ones, don’t get tossed out by accident. The routine, successful traffic gets a light sampling for stats.

{{< insight >}}
**Tail sampling uses OR semantics.** A trace is kept if *any* policy samples it, and policy order doesn't set priority. At scale, with several Collector replicas, run a first tier of Collectors with the `loadbalancingexporter` in front of the sampling tier, so every span of a trace reaches the same replica. Tail sampling needs the whole trace in one place to decide correctly. Without that routing, a trace split across replicas gets judged on half its spans.
{{< /insight >}}

{{< mermaid >}}
flowchart TD
    A[checkout] --> LB
    B[cart] --> LB
    C[promo] --> LB
    LB["Collector tier 1<br/>loadbalancingexporter<br/>routing_key: traceID"]
    LB -->|"all of trace a1b2c3"| R1["tier 2, replica A<br/>tail_sampling"]
    LB -->|"all of trace d4e5f6"| R2["tier 2, replica B<br/>tail_sampling"]
    R1 --> BE[("Tracing backend")]
    R2 --> BE
{{< /mermaid >}}

## Where to Start

Start with the instrumentation gap; it’s the right place, and it’s less overwhelming than it used to be.

Drop the OTel SDK into one service—the entry point for your most important user flow. Stick with the default W3C propagator and set up an OTLP exporter. If the next service downstream is already instrumented or has a framework-level auto-instrumentation agent, the spans will link up automatically. That gives you a two-node trace, which is already a win. Just keep extending the instrumented path, one service at a time, until you’ve got the whole critical chain covered.

These four signals pay for themselves right away: `http.request.method`, `http.response.status_code`, `db.query.text` (sanitized, of course), and a span status of Error with `error.type` set on failures. With just those, you can zero in on every faulty trace, every slow database call, and every error—no more log file scavenger hunts across services.

The things DORA’s numbers can’t show you won’t show up on any dashboard. They’re hiding in the trace—the one that points to the exact service and call that turned a three-minute fix into an hour-long saga. Your dashboard might still be green, but now you’ll know what to grab when that’s not the whole story.