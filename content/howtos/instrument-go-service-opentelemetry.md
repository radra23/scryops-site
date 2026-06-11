---
title: "How to Instrument a Go Service with OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "From zero to traces, metrics, and structured logs in a Go service — using the stable OTel Go SDK, auto-instrumentation for HTTP and gRPC, and a local Collector."
readtime: 7
tags: ["OpenTelemetry", "Tracing", "Observability", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Dependencies: go.opentelemetry.io/otel, otel/sdk, otel/exporters/otlp/otlptrace
2. SDK initialisation: TracerProvider, MeterProvider, LoggerProvider with OTLP exporters
3. Resource attributes: service.name, service.version, deployment.environment
4. Auto-instrumentation for net/http server (otelhttp middleware)
5. Auto-instrumentation for HTTP client (otelhttp transport wrapper)
6. Auto-instrumentation for gRPC (otelgrpc interceptors)
7. Auto-instrumentation for database/sql (otelsql)
8. Manual spans for business logic
9. Adding span attributes and events
10. Error handling: record_exception equivalent in Go, set span status
11. Connecting to local Collector (docker-compose setup)
12. Structured logging with slog + trace context injection

Include: complete working example with go.mod, main.go, docker-compose.yml
Source material note: the standards README identifies language-specific guides as a standards domain
-->
