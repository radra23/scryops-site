---
title: "Should I use OTel collector or ship directly from SDKs?"
date: 2026-03-24
draft: true
answer: "Almost always use the collector. It gives you a central place to batch, retry, filter, and route telemetry without touching your application code again."
excerpt: "Almost always use the collector. It gives you a central place to batch, retry, filter, and route telemetry without touching your application code again."
readtime: 2
tags: ["OpenTelemetry", "OTLP"]
---

Use the collector. Almost always.

## The collector removes the app from the telemetry pipeline

The OTel Collector sits between your application and your backend. This gives you:

- **Batching and retry** — the collector handles transient failures so your app doesn't have to.
- **Filtering and sampling** — drop noisy spans or low-value metrics before they hit your backend (and your bill).
- **Routing** — send traces to Tempo, metrics to Mimir, logs to Loki — all from one pipeline.
- **Decoupling** — change your backend without redeploying your applications.

## Three cases where direct export is justified

- **Serverless functions** where a sidecar collector adds cold start latency.
- **Simple single-service setups** where the collector is more infrastructure than the app itself.
- **Development environments** where you just want to see spans in the console.

{{< obs-otel-collector-vs-sdk >}}

## Two-tier topology: agent per node, gateway per cluster

{{< mermaid >}}
flowchart LR
    app["App<br/>(OTel SDK)"]
    agent["Collector<br/>agent — per node"]
    gateway["Collector<br/>gateway — centralized"]
    be["Backends<br/>(Tempo · Mimir · Loki)"]

    app --> agent --> gateway --> be

    style gateway fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF
{{< /mermaid >}}

The agent handles local buffering and failure isolation; the gateway handles routing, sampling, and auth. You change either layer without touching application code.
