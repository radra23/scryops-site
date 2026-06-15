---
title: "The Evolution of System Understanding"
date: 2026-06-07
draft: true
excerpt: "From reading log files to predicting failures — how our ability to understand complex systems has evolved over 30 years of distributed computing."
readtime: 6
tags: ["Observability", "Philosophy"]
---

For most of computing history, understanding a running system meant reading its logs, watching its dashboards, and writing an alert for the last thing that broke you. That worked when systems were small, stable, and well-understood. It stopped working around 2010, when the industry shifted from monoliths to microservices and the assumptions underneath traditional monitoring became untrue.

## The Monolithic Era

In a monolith, the system is one unit. A problem in the payment code shows up in the payment logs. Slow database queries appear in query time metrics. The instrumentation strategy is obvious — monitor the things you care about, set thresholds based on what normal looks like, and alert when that changes.

This model has genuine advantages. It is simple. Failure modes are predictable. The same issue that broke you last month is likely to break you next month, so you can write a useful alert for it.

The limitation: it only works if you already know what can go wrong.

## The Distributed Systems Problem

When applications fragmented into microservices, the "anticipate the failure mode" model collapsed. A single user request might traverse thirty services. A slow downstream dependency cascades up the call chain, and the error surfaces three hops away from the actual cause. The dashboards look green. Users are already experiencing failures.

This is where the classic three-category problem emerges:

**Known-knowns** — the failure modes you have seen and instrumented for. Payment success/failure rates, transaction volumes, response time thresholds. You have alerts for these and they work.

**Known-unknowns** — gaps you are aware of but have not yet instrumented. You know that regional performance varies but have not yet split your latency metric by region. You know that traffic spikes are coming but have not yet load-tested the new checkout flow.

**Unknown-unknowns** — failure modes you could not have predicted. Novel interaction patterns between services. Complex failure cascades triggered by an edge case in a third-party integration. A new fraud pattern that emerged from a combination of signals nobody thought to watch.

Traditional monitoring covers the first category. The third is invisible to it. Most interesting production incidents land in the third.

{{< obs-knowledge-tiers >}}

## The Telemetry Gap

The data engineers were collecting in the 2000s was sparse by necessity. Storage was expensive; networks were slow; the tooling for querying rich structured data at scale did not exist.

A typical payment event from that era:

```json
{
  "timestamp": "2005-06-14T09:12:00Z",
  "status": "success",
  "amount": 49.99
}
```

What you could ask: did this succeed? That is it.

A contemporary equivalent:

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

{{< mermaid >}}
flowchart LR
    A["2000s · Raw logs<br/>'Did it succeed?'"]
    B["2010s · Metrics<br/>'Is error rate rising?'"]
    C["2012+ · Traces<br/>'Which service is slow?'"]
    D["Today · Rich events<br/>'Why, for whom, in which version?'"]
    A --> B --> C --> D
{{< /mermaid >}}

## The Observability Shift

Distributed tracing — the ability to follow a request's path across service boundaries — offered one of the first systematic responses to the microservices debugging problem. It gave engineers a cross-service view they had never had before.

This was a step toward a broader concept: **observability**. The word comes from control theory. A system is observable if you can reconstruct its internal state from external measurements alone, without needing to insert probes at every possible failure point.

Applied to software: an observable system lets you ask any question about its behaviour and get an answer from the telemetry it emits — not just the questions you anticipated when you wrote the instrumentation.

Three shifts characterise the move from monitored to observable:

**Reactive to proactive.** Traditional monitoring waits for thresholds to fire. Observable systems can surface anomalies before they cross user-visible thresholds — because the telemetry is rich enough to detect degradation patterns early.

**Isolated to connected.** Traditional monitoring tracks each service independently. Observable systems correlate signals across service boundaries, so a slow database query in service A is visible as latency in service B's downstream call.

**Static to dynamic.** Traditional monitoring requires pre-built dashboards for pre-anticipated questions. Observable systems support arbitrary queries — "show me all requests slower than 300ms, grouped by downstream dependency, for the last 15 minutes" — answered at investigation time, not dashboard-build time.

{{< obs-monitoring-shifts >}}

## OpenTelemetry: A Shared Foundation

The practical barrier to observability adoption through most of the 2010s was fragmentation. Each team chose its own tools, its own instrumentation libraries, its own data formats. Correlating signals across services meant reconciling incompatible data models. The observability system itself became a source of operational debt.

OpenTelemetry, launched as a CNCF project in 2019 through the merger of OpenCensus and OpenTracing, addressed this directly. A single vendor-neutral SDK for traces, metrics, and logs. A common wire protocol (OTLP) for all telemetry. A standard Collector for receiving, processing, and forwarding to any backend.

With a shared standard, the instrumentation an engineer writes is portable across backends, queryable alongside signals from other services, and maintainable without specialist knowledge of any particular vendor.

## What Comes Next

The evolution has not stopped.

**Continuous profiling** adds a fourth signal: low-overhead execution profiles collected from production services in real time. Where traces show which request was slow, profiling shows why — which functions consumed CPU, which allocations caused GC pressure, which I/O patterns created contention.

**Threshold-free anomaly detection** reduces the alert-writing burden. Instead of requiring engineers to anticipate failure modes and codify them as thresholds, statistical models — from rolling baselines to time-series anomaly detection — learn normal behaviour from telemetry and surface deviations automatically. This is not a replacement for human judgment — it is a reduction in the minimum detectable signal, surfacing subtle degradations that would never cross a static threshold.

**Business context integration** closes the gap between system health and user impact. A latency spike matters differently if it affects checkout versus a background sync job. Telemetry enriched with business attributes — customer tier, transaction value, revenue impact — lets engineers prioritise not just by severity but by consequence.

The direction is clear: from predefined questions toward arbitrary queryability, from isolated service monitoring toward cross-system correlation, from reactive alerting toward proactive detection. The systems we operate have become more complex than anything the original monitoring model was designed for. The tools are evolving to match.
