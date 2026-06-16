---
title: "The Evolution of System Understanding"
date: 2026-06-07
draft: false
excerpt: "From reading log files to predicting failures — how our ability to understand complex systems has evolved over 30 years of distributed computing."
readtime: 6
tags: ["Observability", "Philosophy"]
---

For most of computing history, understanding a running system meant reading its logs, watching its dashboards, and writing an alert for the last thing that broke you. That worked when systems were small, stable, and well-understood. It stopped working around 2010, when the industry shifted from monoliths to microservices and the assumptions underneath traditional monitoring became untrue.

## The Monolithic Era

In a monolith, the system is one unit. A problem with the payment code shows up in the payment logs. Slow database queries appear in query time metrics. The instrumentation strategy is obvious — monitor the things you care about, set thresholds based on what normal looks like, and alert when that changes.

This model works because failures repeat. If something broke last month, it will probably break again. You write an alert for it and move on.

The limitation: it only works if you already know what can go wrong.

## The Distributed Systems Problem

When applications fragmented into microservices, the “anticipate the failure mode” model collapsed. A single user request might traverse thirty services. A slow downstream dependency cascades up the call chain, and the error surfaces three hops away from the actual cause. The dashboards look green. Users are already experiencing failures.

The classic four-category problem emerges directly from this:

### Charted

These are the failures you have already seen and instrumented. Payment success rates, transaction volumes, response time thresholds. You have alerts for these. They do their job.

### Marked

These are the gaps you know about but haven’t instrumented. You know regional performance varies, but latency is not split by region. You know traffic spikes are coming, but the new checkout flow is untested. You see the gap. Nobody has explored it yet.

### Rumored

These are signals hiding in your telemetry. The payment.provider field has been in every log for a year, but nobody has filtered on it. The data is there. The monitoring is not. This is where you find the fastest wins.

### Here Be Dragons

These are the failures that catch you by surprise. New interactions between services. Cascades triggered by a third-party edge case. Fraud patterns that show up when signals combine in ways nobody expected.

Traditional monitoring only covers the first tier. Most teams spend their time in the second. The fastest wins are hiding in the third. The incidents you remember live in the fourth.

{{< obs-knowledge-tiers >}}

## The Telemetry Gap

In the 2000s, data was sparse because it had to be. Storage cost too much. Networks were slow. Querying rich data at scale was not possible. A typical payment event from that era:

```json
{
  "timestamp": "2005-06-14T09:12:00Z",
  "status": "success",
  "amount": 49.99
}
```

You could only ask one thing: did it succeed? That was the limit.

A current equivalent:

```json
{
  "timestamp": "2026-06-11T09:12:00Z",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "service.name": "checkout-api",
  "payment.amount": 49.99,
  "payment.currency": "GBP",
  "payment.provider": "stripe",
  "payment.method": "credit_card",
  "user.tier": "premium",
  "user.region": "eu-west-1",
  "app.version": "4.2.1",
  "perf.auth_ms": 43,
  "perf.total_ms": 187,
  "http.status_code": 200
}
```

What you can ask: is this payment slow? Is it slow for a specific provider? Is it slow for a specific region? Is it slow for premium-tier users specifically? Is it correlated with a particular app version? These are the questions that turn a "latency spiked" alert into a "stripe auth latency spiked for EU premium users on v4.2.1" root cause.

{{< obs-telemetry-techtree >}}

## The Observability Shift

Distributed tracing let you follow a request across service boundaries. It was the first real answer to the microservices debugging problem.

Tracing solved cross-service request visibility. It didn't solve the harder problem: you could only ask questions you had thought to instrument for. That gap is what observability addresses. In control theory, a system is observable if you can figure out its internal state just from what it emits — no need to add probes at every possible failure point.

Applied to software: an observable system lets you ask any question about its behaviour and get an answer from the telemetry it emits — not just the questions you anticipated when you wrote the instrumentation.

Three shifts characterise the move from monitored to observable:

### Reactive to proactive

Traditional monitoring waits for thresholds to fire. Observable systems can catch degradation patterns before they cross a user-visible threshold — because the telemetry is rich enough to show the signal early.

### Isolated to connected

Monitoring tracks each service independently while observable systems correlate signals across service boundaries, so a slow database query in service A is visible as latency in service B’s downstream call.

### Static to dynamic

Traditional monitoring requires pre-built dashboards for pre-anticipated questions. Observable systems support arbitrary queries — “show me all requests slower than 300ms, grouped by downstream dependency, for the last 15 minutes” — answered at investigation time, not dashboard-build time.

{{< obs-monitoring-shifts >}}

## OpenTelemetry: A Shared Foundation

The practical barrier to observability adoption through most of the 2010s was fragmentation. Each team chose its own tools, its own instrumentation libraries, its own data formats. Correlating signals across services meant reconciling incompatible data models. The observability system itself became a source of operational debt.

OpenTelemetry, formed as a CNCF project in 2019 through the merger of OpenCensus and OpenTracing, addressed this directly. A single vendor-neutral SDK for traces, metrics, and logs. A common wire protocol (OTLP) for all telemetry. A standard Collector for receiving, processing, and forwarding to any backend.

With a shared standard, the instrumentation an engineer writes is portable across backends, queryable alongside signals from other services, and maintainable without specialist knowledge of any particular vendor.

## What Comes Next

### Continuous profiling

Profiling adds a fourth signal to the stack: low-overhead execution profiles collected from production services in real time. Traces show you which request was slow. Profiling shows you why — which functions consumed CPU, which allocations caused GC pressure, which I/O patterns created contention.

### Threshold-free anomaly detection

Instead of making engineers predict every failure mode and write a threshold for it, statistical models — rolling baselines, time-series anomaly detection — learn what normal looks like from the telemetry and surface deviations automatically. It doesn't replace engineering judgment. It lowers the floor on what you can detect, catching subtle degradations that would never fire a static alert.

### Business context integration

Not every degradation is equally urgent. A latency spike during checkout costs revenue. The same spike during a background sync can wait. Telemetry enriched with business attributes — customer tier, transaction value, revenue impact — lets engineers prioritise by consequence, not just severity.

The infrastructure for arbitrary-query observability exists. The gap now is not tooling — it is the organizational habit of building systems that emit enough context to be questioned at all.
