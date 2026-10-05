---
title: "What's the real difference between profiling and tracing?"
date: 2026-10-01
draft: false
answer: "Tracing tells you which path a request took and how long each hop took. Profiling tells you what your CPU was actually doing during those hops. They're complementary — use both."
excerpt: "Tracing tells you which path a request took and how long each hop took. Profiling tells you what your CPU was actually doing during those hops. They're complementary — use both."
readtime: 2
tags: ["Profiling", "Tracing"]
card:
  title: "Profiling vs. tracing: what's the difference?"
---

{{< obs-profiling-vs-tracing >}}


## Tracing locates latency across services

Distributed tracing follows a request through your system. Each span represents a unit of work — an HTTP call, a database query, a message consumed from a queue.

Tracing answers: **Where did time go across services?**

## Profiling locates latency inside a service

Profiling samples your CPU at regular intervals (or your memory allocator every N bytes) and records the call stack. It tells you which functions consumed the most resources.

Profiling answers: **Where did time go within a service?**

## A trace shows the 800ms span; a profile shows why it took 800ms

A trace might show that `service-B` took 800ms to respond. But it won't tell you *why*. GC pressure? A hot loop in serialization code? A regex that backtracks on certain inputs?

Profiling fills that gap. When you can link a trace span to the profile samples taken while that span was running, you get both halves: the request path *and* the code-level bottleneck.

The link works by labelling. While a span is active, the profiler tags each stack sample with that span's ID, so a slow span can pull up exactly the samples it caused. A profile that only shares the span's time window would also include every other request running at the same moment.

This explains time the span spent busy on the CPU. If it spent the 800ms waiting on a lock, a socket or a disk, a CPU profile shows almost nothing, and you need an off-CPU or contention profile instead.

{{< mermaid caption="Fig. — The slow span pulls up the CPU samples labelled with its span ID, turning where time went into why it went there." >}}
flowchart TD
    req["Incoming request"]
    sA["service-A span<br/>(10ms)"]
    sB["service-B span<br/>(800ms)"]
    sC["service-C span<br/>(5ms)"]
    prof["CPU profile<br/>for service-B<br/>↳ hot loop in<br/>serialisation"]
    rc["Root cause<br/>identified"]

    req --> sA --> sB --> sC
    sB -.->|"samples labelled<br/>with span ID"| prof
    prof --> rc

    style sB fill:#2A1A1A,stroke:#CC4444,color:#FF6060,stroke-width:3px
    style prof fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style rc fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
{{< /mermaid >}}

## Tools that link trace spans to CPU profiles

- **Grafana** calls it [traces to profiles](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-profiles/): a Tempo span opens the matching Pyroscope profile. It needs a span-profiling integration in the app's SDK, available today for [Go, Java, .NET, Python and Ruby](https://grafana.com/docs/pyroscope/latest/configure-client/trace-span-profiles/).
- **Datadog** links them through [Code Hotspots](https://docs.datadoghq.com/profiler/connect_traces_and_profiles/), a Profiles tab on each span, when both its tracer and profiler are running.
- **OpenTelemetry** is standardising it: the [Profiles signal](https://opentelemetry.io/blog/2026/profiles-alpha/) reached public Alpha in March 2026 and carries trace and span IDs on samples, so the link can stop being vendor-specific as backends adopt it.

Profilers that attach from outside the process, such as eBPF agents, mostly can't see which span is active, so check for span-level linking before you pick one for this job.

Linked trace-profile views are the fastest path from "this request was slow" to "this function is the reason."
