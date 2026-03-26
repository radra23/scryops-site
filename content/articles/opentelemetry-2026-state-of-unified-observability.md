---
title: "OpenTelemetry in 2026: The State of Unified Observability"
date: 2026-03-25
draft: false
excerpt: "After years of fragmentation, the ecosystem is converging. We take stock of where OTel stands, what's still missing, and the battles yet to be fought."
readtime: 8
tags: ["OpenTelemetry", "Tracing", "Metrics", "Logs"]
---

After years of fragmentation, the observability ecosystem is finally converging around OpenTelemetry. But convergence doesn't mean completion — and the gap between "standard" and "production-ready" still trips up teams daily.

## Where OTel stands today

The OpenTelemetry project has reached general availability for traces, metrics, and logs across most major languages. The collector has become the de facto pipeline component, and OTLP is now supported natively by every major backend.

But adoption is uneven. Traces are mature. Metrics are getting there. Logs are still catching up — and profiling is only just entering the picture.

## What's still missing

- **Profiling support** is in early stages. The profiling signal was accepted into the spec, but SDK support varies widely.
- **Real-time tail sampling** at the collector level remains brittle for high-throughput systems.
- **Semantic conventions** are still evolving, which means instrumenting consistently across services requires manual effort.
- **Configuration complexity** — setting up a production-grade collector pipeline with proper batching, retry, and routing is still harder than it should be.

## The battles ahead

The biggest tension in OTel's future isn't technical — it's political. Vendor extensions, proprietary exporters, and "OTel-compatible" claims that don't quite hold up are creating a new layer of fragmentation beneath the standard.

Teams that invest in understanding OTel at the protocol level — not just the SDK level — will be best positioned to navigate this.

> The standard is the floor, not the ceiling. Build above it.
