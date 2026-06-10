---
title: "How to Set Up an OTel Collector Pipeline for Multi-Cloud Telemetry"
date: 2026-06-10
draft: true
excerpt: "Configure OpenTelemetry Collectors to gather telemetry from AWS, Azure, and GCP workloads and route it through a central aggregation layer — with cluster identity, cost tagging, and unified output to a single backend."
readtime: 7
tags: ["Multi-Cloud", "OpenTelemetry", "Collector", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Deploy per-cloud gateway Collectors (EKS, AKS, GKE DaemonSet configs)
2. Add cloud identity resource attributes (cloud.provider, cloud.region, cloud.account.id)
3. Configure OTLP/gRPC between regional gateways and central aggregator
4. Set up TLS and authentication between clouds
5. Add cost-allocation labels as resource attributes (team, service, environment)
6. Configure load balancing exporter for high-availability central layer
7. Verify end-to-end: trace from AWS service to central backend
8. Cost: estimate data volumes and configure sampling per cloud

Include: annotated Collector config YAML for each cloud layer
-->
