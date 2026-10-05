---
title: "The dashboard was green, but the request was broken."
date: 2026-09-27
draft: false
excerpt: "Metrics tell you how the crowd is doing. Logs tell you what one service saw. A trace tells you what one request went through, and at 2 a.m. that is usually the question you are asking."
readtime: 6
description: "A green dashboard hid a broken checkout. How distributed tracing, OpenTelemetry and tail-based sampling find the one failing request your metrics average away."
tags: ["Tracing", "Observability", "OpenTelemetry", "Sampling", "Debugging"]
card:
  panel:
    - {key: error_rate, value: "0.3%", state: ok}
    - {key: latency.p50, value: "42ms", state: ok}
    - {key: health_checks, value: "4/4", state: ok}
    - {key: checkout.total, value: "$0.00", state: warn, label: "200 OK, no error"}
---

It’s 2 a.m., and your phone almost vibrates off the table. You stumble to your laptop, open the dashboard, and see a sea of green: error rate at 0.3%, latency p50 at 42ms, health checks all smiling. You start to think this is just another false alarm. Twenty minutes later, another engineer hops on and drops a user complaint into Slack. Turns out, checkout is broken—but only for folks using a promo code on a cart with one very specific product category.

Your metrics had no idea.

You burn another forty minutes playing log detective, piecing clues from four different services. If you'd had a distributed trace, you could have solved it in thirty seconds: follow the spans, spot the database call that handed back a null discount, and watch it travel downstream as a perfectly respectable $0.00 total. A mimic posing as a treasure chest: no error, no alarm, nothing until someone opens the lid.

This isn’t a rare edge case. I’ve seen this exact shape more than once: a value that is wrong but valid, travelling through healthy services and averaging away into a green dashboard. It’s the classic failure mode when you rely on metrics first, especially in systems that were never a tidy monolith to begin with.

{{< obs-green-dashboard-vs-trace fig="1" >}}

## The Three Witnesses

Picture your observability stack as three types of witnesses at the scene of an incident.

Logs are your classic eyewitnesses: detailed, specific, and a bit myopic. Each one saw exactly what happened in its own little corner, but none of them caught the whole show. Trying to rebuild a single request from five different log streams is slow, manual work, and nobody wants to do it at 2 a.m.

Metrics are the statisticians in the room. They’ll tell you how often things happen, how fast, and in what total. Perfect for capacity planning, SLOs, and trend-spotting. But if you want to know why *this* request failed, metrics shrug—they’re designed to toss out the individual stories and focus on the crowd.

Traces are your surveillance footage. They follow a single request from the front door to the exit, catching every service hop, every database query, and every millisecond spent twiddling its thumbs. Here the unit you study is the request itself: richer than any single log line, more specific than any metric. That’s a whole different way of asking questions.

| Witness | Answers | Misses |
|---------|---------|--------|
| Logs | What happened in this service | The rest of the request |
| Metrics | How often, how fast, how many | Which request, and why |
| Traces | What this request went through | Trends, unless aggregated |

## The Dashboard Reflex

In 2018, Nicole Forsgren, Jez Humble and Gene Kim published *Accelerate*, one of the most influential engineering books of the decade, built on the research of the DevOps Research and Assessment (DORA) program. It gave the industry something it badly needed: a shared vocabulary for delivery performance. Its four metrics (deployment frequency, lead time for changes, change failure rate, and mean time to restore) became the benchmark you'll measure every engineering team against. DORA has since moved on: in 2023 time to restore became failed deployment recovery time, and in 2024 a fifth metric, deployment rework rate, joined the set. The idea stuck. The research holds up, and the framework was exactly the right tool for the job it was built for.

But there was a sneaky side effect. Once software delivery got boiled down to four tidy numbers, a lot of teams started expecting the dashboard to have all the answers. The reflex kicked in: something’s wrong? Find the metric. Build the dashboard. Stare at the number.

Here’s where the wires get crossed. DORA metrics are all about your delivery process—they show how well your team ships software over time. They’re not built to diagnose a single failed request. Mean time to restore might tell you last quarter’s average was 47 minutes, but it won’t say a word about why tonight’s incident dragged on for an hour: which service tripped up, which team owned it, which code path went astray, or which upstream quietly ghosted you.

That mysterious hour? That’s distributed tracing’s home turf. Delivery metrics can tell you things are slowing down, but only a trace will show you exactly where this one began its journey to nowhere.

## Why Tracing Didn't Win Sooner

Distributed tracing has existed since Google published the [Dapper paper](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/) in 2010. Twitter open-sourced Zipkin in 2012, and Uber open-sourced Jaeger in 2017. If the value was always there, why did mainstream adoption take another decade?

There were really two big roadblocks.

First up: instrumentation fragmentation. Tracing used to mean picking a tracer or a vendor (Zipkin, Jaeger, Lightstep, Datadog) and bolting its client library onto every service in your call graph. It was sticky, pricey, and migrating later was a headache. OpenTracing and OpenCensus tried to help, but having two standards just meant double the confusion. They finally merged into OpenTelemetry in 2019. If you had fifty services, that meant fifty SDK integrations, tied to one backend, before you saw a single complete trace, and a lot of teams just decided it wasn’t worth the hassle.

Second: the sampling trap. Capturing every single trace is expensive—store every span from every request and your storage bill balloons with every user click. The usual fix was head-based sampling: flip a coin at the front door, trace 5 or 10% of requests, and hope the sample tells the story.

But head-based sampling is flying blind. It tosses traces before it knows if they’re interesting. The slow requests, the errors, the weird edge cases—they get sampled just as often as the boring, happy-path traffic. You end up with a sample that’s [statistically fair](/articles/sampling-strategy/), but mostly full of traces you’ll never care about.

## What Changed

OpenTelemetry came along and fixed the fragmentation mess. Now there’s one API and spec, with an SDK for every language, and the W3C Trace Context standard (that’s the `traceparent` header) keeps spans passing smoothly without vendor lock-in. Auto-instrumentation agents—bytecode for Java, monkey-patching for Python and Node.js—let you instrument existing services without touching the code. The sticky vendor lock-in that made tracing a pain? That’s mostly history.

Tail-based sampling solved the sampling trap. Instead of making a snap decision at the start, the OpenTelemetry Collector’s [`tail_sampling` processor](/howtos/configure-collector-tail-sampling/) buffers spans and waits. It doesn’t know exactly when a trace is done, so it waits a set `decision_wait` after the first span shows up, then makes the call. Spans that arrive after the decision can end up judged separately, which leaves you with half a trace, so set `decision_wait` longer than your slowest normal request (and turn on the decision cache). Within that window, you can keep every trace with an error, every slowpoke over your latency threshold, and just a pinch of the rest:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 100000   # ≈ traces/sec × decision_wait, plus headroom
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow-traces
        type: latency
        latency: {threshold_ms: 1000}
      - name: silent-business-failures
        type: boolean_attribute
        boolean_attribute: {key: app.discount.missing, value: true}
      - name: baseline-sample
        type: probabilistic
        probabilistic: {sampling_percentage: 5}
```

One catch: the checkout bug from the top of this article would have slipped past the first two policies. It returned 200 OK, and it was fast. Tail sampling can only keep what the span says is interesting, so teach your code to say it. When the discount lookup comes back null, set `app.discount.missing=true` on the span, and the `silent-business-failures` policy keeps every one of those traces.

{{< obs-head-vs-tail-sampling fig="2" >}}

Now the traces you actually care about, the weird, here-be-dragons ones, don’t get tossed out by accident. The routine, successful traffic gets a light sampling for stats.

The trade-off is memory: the Collector holds every span for `decision_wait`, so size `num_traces` to roughly your traces per second times `decision_wait`, with headroom.

{{< insight >}}
**Tail sampling uses OR semantics.** A trace is kept if *any* policy samples it, unless a drop policy matches it, and policy order doesn't set priority. At scale, with several Collector replicas, run a first tier of Collectors with the `loadbalancingexporter` in front of the sampling tier, so every span of a trace reaches the same replica. Tail sampling needs the whole trace in one place to decide correctly. Without that routing, a trace split across replicas gets judged on half its spans.
{{< /insight >}}

{{< mermaid alt="A first Collector tier with the load-balancing exporter routes every span of a trace to the same tail-sampling replica" caption="Fig. 3 — Route by trace ID first, so each sampling replica sees whole traces." >}}
flowchart TD
    A[checkout] -->|"a1b2c3, d4e5f6"| LB
    B[cart] -->|"a1b2c3"| LB
    C[promo] -->|"d4e5f6"| LB
    LB["Collector tier 1<br/>loadbalancingexporter<br/>routing_key: traceID"]
    LB -->|"all of trace a1b2c3"| R1["tier 2, replica A<br/>tail_sampling"]
    LB -->|"all of trace d4e5f6"| R2["tier 2, replica B<br/>tail_sampling"]
    R1 --> BE[("Tracing backend")]
    R2 --> BE
{{< /mermaid >}}

## Where to Start

You don’t need fifty services instrumented to get value. You need one request path, traced end to end.

1. Drop the OTel SDK into one service: the entry point for your most important user flow.
2. Stick with the default [W3C propagator](/guides/otel-context-propagation/) and set up an OTLP exporter.
3. Instrument the next service downstream, or let a framework-level auto-instrumentation agent do it. The spans link up automatically, and a two-node trace is already a win.
4. Keep extending the instrumented path, one service at a time, until the whole critical chain is covered.

These four signals pay for themselves right away: `http.request.method`, `http.response.status_code`, `db.query.text` (sanitized, of course), and a span status of Error with `error.type` set on failures. With just those, you can zero in on every faulty trace, every slow database call, and every error—no more log file scavenger hunts across services.

Then add one attribute your business cares about on the critical path, such as whether a promo code was applied and what discount came back (the `app.discount.missing` flag from the sampling policy above). That is the attribute that would have found the 2 a.m. checkout bug.

Next time the dashboard is green and checkout is broken, you won’t be piecing it together from four log streams. You’ll open one trace and watch the $0.00 discount happen.