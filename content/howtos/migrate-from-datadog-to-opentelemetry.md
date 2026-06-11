---
title: "How to Migrate from the Datadog Agent to OpenTelemetry Collector"
date: 2026-06-10
draft: true
excerpt: "A step-by-step migration walkthrough: inventory your existing Datadog instrumentation, run OTel alongside the Datadog agent, validate signal equivalence, then cut over — without losing coverage or triggering incidents."
readtime: 8
tags: ["OpenTelemetry", "Collector", "Observability", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Pre-migration: inventory all instrumentation (APM, infra, logs, custom metrics)
2. Install OTel Collector alongside Datadog agent (side-by-side phase)
3. Configure OTel SDK to send to Collector (keep Datadog agent running)
4. Use Collector's Datadog exporter to dual-ship to Datadog and new backend
5. Compare dashboards: validate p50/p95/p99 latency and error rates match
6. Migrate custom metrics: Datadog custom metrics → OTel metrics with semantic conventions
7. Log migration: configure OTel log receiver to replace Datadog log agent
8. Infrastructure metrics: replace dd-agent infra collection with OTel host metrics receiver
9. Cutover: disable Datadog agent per service
10. Cleanup: remove Datadog SDK dependencies from application code

Include: Collector config YAML for dual-ship setup, validation checklist
-->
