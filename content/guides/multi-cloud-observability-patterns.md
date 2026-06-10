---
title: "Multi-Cloud Observability: One View Across AWS, Azure, and GCP"
date: 2026-06-10
draft: true
excerpt: "Running workloads across multiple cloud providers creates fragmented observability by default. This guide covers the architectural patterns, OTel Collector configurations, and data management strategies for unified multi-cloud visibility."
readtime: 10
tags: ["Multi-Cloud", "OpenTelemetry", "Collector", "Observability", "Cost"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. The multi-cloud observability challenge: siloed data, vendor-specific formats
2. OpenTelemetry as the unifying collection layer
3. OTel Collector deployment patterns for multi-cloud:
   - Agent-per-cloud + central aggregator
   - Regional gateway collectors
   - Cloud-native sidecar injection
4. Cross-cloud trace correlation: propagating context across cloud boundaries
5. Unified metrics pipeline: scraping CloudWatch, Azure Monitor, GCP Cloud Monitoring via OTel
6. Cost optimisation: routing high-volume signals to cheaper backends
7. Data residency considerations for multi-cloud telemetry
8. Reference architecture diagram (Mermaid)
9. Avoiding cloud-vendor-specific exporters in favour of OTLP
-->
