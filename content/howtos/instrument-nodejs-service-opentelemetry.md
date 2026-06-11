---
title: "How to Instrument a Node.js Service with OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "Add OpenTelemetry to a Node.js service — auto-instrumentation for Express, Fastify, and HTTP clients, plus manual spans for business logic, all routed through a local Collector."
readtime: 7
tags: ["OpenTelemetry", "Tracing", "Observability", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Dependencies: @opentelemetry/sdk-node, @opentelemetry/auto-instrumentations-node
2. The tracing.js initialisation file (must be loaded before application code)
3. SDK setup: NodeSDK with OTLP exporter and resource attributes
4. Auto-instrumentation: Express, HTTP, gRPC, Redis, PostgreSQL/MySQL
5. Manual spans: tracer.startActiveSpan()
6. Async context propagation: AsyncLocalContextManager (why this is critical in Node.js)
7. Error handling: span.recordException, span.setStatus
8. TypeScript support: types package
9. Environment variable configuration (OTEL_EXPORTER_OTLP_ENDPOINT etc.)
10. Connecting to local Collector

Include: complete working example, package.json, tracing.js, server.ts
Source material note: language-specific guides are a standards domain in the standards README
-->
