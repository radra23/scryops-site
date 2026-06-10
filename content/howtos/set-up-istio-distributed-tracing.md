---
title: "How to Enable Distributed Tracing with Istio and OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "Configure Istio to emit distributed traces via OpenTelemetry, connect mesh-level spans to application-level spans, and visualise end-to-end service-to-service traces in Grafana Tempo."
readtime: 7
tags: ["Service Mesh", "Kubernetes", "Tracing", "OpenTelemetry", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Enable Istio tracing with OTel provider (IstioOperator config)
2. Configure sampling rate for mesh traces
3. Point Istio to OTel Collector OTLP endpoint
4. Application-side: propagating W3C Trace Context through service calls
5. Connecting Istio sidecar spans to application spans (parent-child relationship)
6. Configure Tempo as the trace backend
7. Grafana: link service graph to trace explorer
8. Verify end-to-end trace across two services
9. Common issue: B3 vs W3C context propagation mismatch

Include: IstioOperator YAML, Collector config, Grafana datasource config
-->
