---
title: "Observability vs. Monitoring: Why the Distinction Matters"
date: 2026-06-07
draft: true
excerpt: "Monitoring tells you when something is wrong. Observability lets you figure out why. The gap between them is where most teams get stuck."
readtime: 5
tags: ["Observability", "Monitoring", "Philosophy"]
---

Both words get used interchangeably. They are not the same thing, and the difference is not semantic. It determines what questions you can answer when something breaks.

## The Definition

**Monitoring** is the practice of watching known failure modes. You decide in advance what matters — CPU usage, error rate, latency, queue depth — and you alert when those metrics cross thresholds. Monitoring answers the question: *is this thing I'm watching within acceptable bounds?*

**Observability** is the property of a system that lets you understand its internal state from its external outputs. An observable system lets you ask arbitrary questions — questions you did not think to ask before the incident — and get answers from the telemetry the system emits. Observability answers the question: *what is happening inside this system right now, and why?*

Monitoring requires prior knowledge of what can go wrong. Observability does not.

## Why the Distinction Matters in Production

A monitored system without observability will eventually produce an incident that none of the monitors catch. Not because the monitors are wrong — because the failure mode was not anticipated when they were written.

The pattern is familiar: the dashboard is green, the thresholds have not fired, and users are already experiencing degraded service. The alert fires three minutes later, or not at all, because the failure did not look like any of the known failure modes. The on-call engineer opens the system and has no tools to ask "what changed, where, and for which users?" They have dashboards built for questions that were already answered.

Observability covers the unknown unknowns. Monitoring covers the known ones. You need both.

## The Five Requirements for an Observable System

A system that is truly observable — not just monitored — needs five capabilities:

**1. Comprehensive instrumentation.** Every service emits telemetry for every operation that matters. Not just when something breaks — continuously. If a service only logs errors, you cannot distinguish "no requests" from "all requests succeeding" from "all requests being dropped before they arrive."

**2. Consistent naming.** If one service calls the same concept `user_id` and another calls it `userId` and a third calls it `customerId`, you cannot write a query that spans all three. Shared vocabulary — semantic conventions — is what makes cross-service analysis possible. Without it, every team's telemetry is only queryable by that team.

**3. Context propagation.** As a request moves through your system, its identity must travel with it. The trace ID that identifies a request in service A must be present in service B's spans, service C's logs, and the database query it triggers. Without propagation, you have islands of data that cannot be connected.

**4. Centralised collection.** Telemetry emitted by individual services is only useful when it can be queried together. A Collector or aggregation layer that receives signals from all services — normalises them, routes them, and forwards them to storage — is the infrastructure that makes cross-service queries possible.

**5. Flexible analysis.** Raw telemetry answers no questions on its own. The tooling that queries it — the ability to filter by any attribute, aggregate over any dimension, correlate spans to logs, and ask questions that were not anticipated at instrumentation time — is what converts telemetry into understanding.

Most teams have partial versions of all five. The gaps between "partial" and "complete" are where incidents become prolonged.

## The Practical Test

The clearest way to distinguish a monitored system from an observable one is to ask what happens during an incident you have never seen before.

In a monitored system: the on-call engineer looks at the dashboards they have, does not find the answer there, escalates to someone who knows the code, and resolves the incident based on expertise rather than evidence.

In an observable system: the on-call engineer queries the telemetry with arbitrary questions — "show me all requests slower than 500ms, grouped by downstream dependency, for the last 30 minutes" — and finds the answer in the data, without needing to know the codebase.

The goal of instrumentation is to reach the second state. Not just for incidents you have already seen. For any incident.

<!-- TODO: Add section contrasting specific tool categories: APM vs Observability platforms -->
<!-- TODO: Add section on the cost dimension: observability generates more data, costs more to store -->
<!-- TODO: Cross-reference to observability-maturity-model.md for the progression from monitoring to observability -->
