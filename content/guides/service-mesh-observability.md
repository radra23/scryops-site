---
title: "Service Mesh Observability: What Istio and Linkerd Give You for Free"
date: 2026-06-10
draft: true
excerpt: "A service mesh instruments every call between services at the infrastructure layer — without touching application code. A guide to what you get from the mesh, what you still need to add yourself, and how to integrate mesh telemetry with your existing observability stack."
readtime: 10
tags: ["Service Mesh", "Kubernetes", "Tracing", "Metrics", "OpenTelemetry"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. What a service mesh instruments automatically: latency, error rate, request volume per service pair
2. What it does NOT give you: business context, internal application traces, log correlation
3. Istio telemetry:
   - Prometheus metrics (istio_requests_total, istio_request_duration)
   - Envoy access logs
   - Distributed tracing with Zipkin/Jaeger/OTel
4. Linkerd telemetry:
   - Prometheus metrics via linkerd-viz
   - Per-route metrics
   - OTel integration
5. Connecting mesh traces to application traces (B3 vs W3C context propagation)
6. mTLS observability: monitoring certificate health and connection security
7. Traffic policy observability: canary, circuit breaker, retries as telemetry
8. Kiali / Linkerd Viz vs custom dashboards
9. Cost of mesh telemetry: storage and cardinality considerations
-->
