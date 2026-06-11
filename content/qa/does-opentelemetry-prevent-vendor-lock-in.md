---
title: "Does OpenTelemetry actually prevent vendor lock-in?"
date: 2026-06-10
draft: true
answer: "Partially. OTel standardises the instrumentation layer — your application code stays vendor-neutral. But you can still be locked in at the backend (storage, query, dashboards). OTel is insurance against re-instrumentation, not against switching costs entirely."
excerpt: "Partially. OTel standardises instrumentation so you never touch application code again when switching backends. But backend, query language, and dashboard lock-in still exist. OTel solves the most painful part."
readtime: 2
tags: ["OpenTelemetry", "Observability", "Cost"]
---

<!-- TODO: Draft this Q&A -->
<!--
Answer should cover:
- What OTel neutralises: SDK instrumentation, agent configuration, data format
- What OTel doesn't neutralise: backend storage, PromQL/LogQL/TraceQL queries, dashboards
- The real saving: never having to re-instrument when you switch vendors
- Practical example: switching from Datadog to Grafana Cloud with OTel already in place
- Caveats: vendor-specific features (Datadog APM correlation, profiling integrations)
- The Collector as the routing layer: multi-destination during migration
-->
