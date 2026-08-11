---
title: "What's the real difference between profiling and tracing?"
date: 2026-03-23
draft: true
answer: "Tracing tells you which path a request took and how long each hop took. Profiling tells you what your CPU was actually doing during those hops. They're complementary — use both."
excerpt: "Tracing tells you which path a request took and how long each hop took. Profiling tells you what your CPU was actually doing during those hops. They're complementary — use both."
readtime: 2
tags: ["Profiling", "Tracing"]
---

{{< obs-profiling-vs-tracing >}}


## Tracing locates latency across services

Distributed tracing follows a request through your system. Each span represents a unit of work — an HTTP call, a database query, a message consumed from a queue.

Tracing answers: **Where did time go across services?**

## Profiling locates latency inside a service

Profiling samples your CPU (or memory allocator) at regular intervals and records the call stack. It tells you which functions consumed the most resources.

Profiling answers: **Where did time go within a service?**

## A trace shows the 800ms span; a profile shows why it took 800ms

A trace might show that `service-B` took 800ms to respond. But it won't tell you *why*. Was it a slow database query? GC pressure? A hot loop in serialization code?

Profiling fills that gap. When you can link a trace span to a CPU profile for the same time window, you get the complete picture: the request path *and* the code-level bottleneck.

{{< mermaid caption="Fig. — A slow trace span links via trace context to a CPU profile for the same window, turning where time went into why it went there." >}}
flowchart TD
    req["Incoming request"]
    sA["service-A span<br/>(10ms)"]
    sB["service-B span<br/>(800ms)"]
    sC["service-C span<br/>(5ms)"]
    prof["CPU profile<br/>for service-B<br/>↳ hot loop in<br/>serialisation"]
    rc["Root cause<br/>identified"]

    req --> sA --> sB --> sC
    sB -.->|"link via<br/>trace context"| prof
    prof --> rc

    style sB fill:#2A1A1A,stroke:#CC4444,color:#FF6060,stroke-width:3px
    style prof fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style rc fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
{{< /mermaid >}}

## Tools that link trace spans to CPU profiles

- **Grafana** links Tempo traces to Pyroscope profiles.
- **Parca** can correlate eBPF profiles with trace context.
- **Datadog** offers unified trace + profile views natively.

Linked trace-profile views are the fastest path from "this request was slow" to "this function is the reason."
