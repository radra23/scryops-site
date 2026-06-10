---
title: "Why Traditional Monitoring Isn't Enough"
date: 2026-06-07
draft: true
excerpt: "The dashboard worked. The threshold didn't fire. But users were already angry. Here is why monitoring-as-usual fails modern distributed systems."
readtime: 6
tags: ["Observability", "Monitoring", "Philosophy"]
---

Traditional monitoring was designed for a different kind of system. It works well when you have a small number of services, failure modes you have seen before, and traffic patterns that are predictable enough for static thresholds to mean something.

Modern distributed systems are none of those things.

## What Traditional Monitoring Assumes

Traditional monitoring is built on a prediction: *I know what can go wrong.* The engineer writes down the known failure modes, picks a metric for each one, sets a threshold, and wires up an alert. When the metric crosses the line, the alert fires.

This model has real strengths. It is simple, predictable, and cheap to reason about. For well-understood systems with stable behaviour, it works.

The problem is not the model itself. The problem is what it cannot do.

## The Failure Modes It Misses

**Gradual degradation.** A memory leak that increases p99 latency by 2ms per hour will not cross a static threshold for hours. By the time the alert fires, the service is already failing for a meaningful slice of users. Static thresholds are point-in-time checks — they have no concept of trend.

**Interaction effects.** In a monolith, a slow database query shows up in one place. In a microservices system, that same query can cascade — the service that calls the database becomes slow, the service that calls that service queues up requests, the service upstream starts timing out, and the failure surfaces three hops away from the actual cause. Each individual metric may look acceptable. The system-level behaviour is not.

**Novel failure modes.** The alerts you write protect against the failures you have already seen. The first time a new failure mode appears — a new dependency, a new traffic pattern, a configuration change with an unexpected interaction — there is no alert for it because nobody knew to write one. The system looks green until users tell you otherwise.

**Cardinality blindness.** An error rate alert tells you that 2% of requests are failing. It cannot tell you whether that 2% is spread evenly across all users or concentrated entirely in one tenant, one region, or one endpoint. Traditional monitoring aggregates by design — the aggregation hides the structure that would tell you where to look.

## The Shared Vocabulary Problem

Traditional monitoring also has a tooling fragmentation problem that becomes severe at scale.

Each team picks the monitoring tools that suit their service. Prometheus for one, CloudWatch for another, Datadog for a third. Each tool uses its own data model, its own query language, its own concept of what a service is. When an incident spans multiple services — which is most of the interesting incidents — the on-call engineer is switching between three UIs with incompatible mental models, trying to correlate data that was never designed to be correlated.

This is not a failure of tools. It is a failure of the underlying approach: monitoring treated each service in isolation because the tools for cross-service correlation did not exist.

OpenTelemetry exists to solve this. A shared data format, a shared collection pipeline, a shared vocabulary of attribute names — these are the infrastructure for cross-service observability that traditional monitoring never had.

## Where Traditional Monitoring Still Belongs

Traditional monitoring is not obsolete. It remains the right tool for known failure modes with clear operational thresholds. Disk usage at 90% should page someone. Certificate expiry within 30 days should alert. These are binary checks on well-understood conditions.

The mistake is treating this kind of monitoring as the whole of the problem. Known failure modes are a subset of all possible failure modes — a shrinking subset as systems grow more complex.

The argument for observability is not that thresholds are wrong. It is that thresholds alone leave you blind to the majority of what can go wrong in a distributed system. Traditional monitoring is the floor. Observability is the ceiling.

## The Unified Telemetry Model

What changes when you move from traditional monitoring to observability is not the alerting — you keep the alerts — it is the instrumentation model.

Traditional monitoring instruments services individually, for specific known signals, using whatever tool each team prefers. Observable systems instrument services uniformly, for rich structured events with arbitrary attributes, using a shared telemetry standard. The same instrumentation that feeds your SLO alerts also feeds ad-hoc incident investigation. The data does not change — the vocabulary and the pipeline do.

The result is a system where the question "what is happening right now and why" has an answer that does not require escalating to the engineer who knows the code.

<!-- TODO: Add concrete before/after scenario: same incident, traditional monitoring vs observability approach -->
<!-- TODO: Add section on the cost of traditional monitoring at scale: alert fatigue, false positives, coverage gaps -->
<!-- TODO: Cross-reference to observability-vs-monitoring.md for the definitional distinction -->
