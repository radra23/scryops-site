---
title: "Should I use OTel collector or ship directly from SDKs?"
date: 2026-03-24
draft: false
answer: "Almost always use the collector. It gives you a central place to batch, retry, filter, and route telemetry without touching your application code again."
tags: ["OpenTelemetry", "OTLP"]
---

## The short answer

Use the collector. Almost always.

## Why the collector wins

The OTel Collector sits between your application and your backend. This gives you:

- **Batching and retry** — the collector handles transient failures so your app doesn't have to.
- **Filtering and sampling** — drop noisy spans or low-value metrics before they hit your backend (and your bill).
- **Routing** — send traces to Tempo, metrics to Mimir, logs to Loki — all from one pipeline.
- **Decoupling** — change your backend without redeploying your applications.

## When direct export makes sense

- **Serverless functions** where a sidecar collector adds cold start latency.
- **Simple single-service setups** where the collector is more infrastructure than the app itself.
- **Development environments** where you just want to see spans in the console.

## Recommended architecture

```
App (OTel SDK) → OTel Collector (agent mode, per-node)
                    → OTel Collector (gateway mode, centralized)
                        → Backend (Tempo, Mimir, Loki, etc.)
```

The two-tier collector setup (agent + gateway) gives you the best balance of reliability, flexibility, and operational simplicity.
