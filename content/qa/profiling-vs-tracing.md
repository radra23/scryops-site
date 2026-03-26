---
title: "What's the real difference between profiling and tracing?"
date: 2026-03-23
draft: false
answer: "Tracing tells you which path a request took and how long each hop took. Profiling tells you what your CPU was actually doing during those hops. They're complementary — use both."
tags: ["Profiling", "Tracing"]
---

## Tracing

Distributed tracing follows a request through your system. Each span represents a unit of work — an HTTP call, a database query, a message consumed from a queue.

Tracing answers: **Where did time go across services?**

## Profiling

Profiling samples your CPU (or memory allocator) at regular intervals and records the call stack. It tells you which functions consumed the most resources.

Profiling answers: **Where did time go within a service?**

## Why you need both

A trace might show that `service-B` took 800ms to respond. But it won't tell you *why*. Was it a slow database query? GC pressure? A hot loop in serialization code?

Profiling fills that gap. When you can link a trace span to a CPU profile for the same time window, you get the complete picture: the request path *and* the code-level bottleneck.

## Tools that bridge the gap

- **Grafana** links Tempo traces to Pyroscope profiles.
- **Parca** can correlate eBPF profiles with trace context.
- **Datadog** offers unified trace + profile views natively.
