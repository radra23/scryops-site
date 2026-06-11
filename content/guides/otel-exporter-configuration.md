---
title: "Configuring OTel Exporters: Getting Telemetry from Your Code to Your Backend"
date: 2026-06-10
draft: true
excerpt: "The exporter is the last step in the OTel pipeline — the piece that sends your spans, metrics, and logs to a backend. A guide to configuring OTLP, Prometheus, and Jaeger exporters correctly, with production-ready settings for batching, retry, and authentication."
readtime: 8
tags: ["OpenTelemetry", "Collector", "Observability", "Best Practices"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. The exporter's role in the OTel pipeline (SDK → Exporter → Backend or Collector)
2. The preferred pattern: always export to the OTel Collector, not directly to backends
   - Why: retries, batching, routing, and vendor-switching happen in the Collector
3. OTLP exporter configuration:
   - OTLP/gRPC vs OTLP/HTTP: when to use each
   - Endpoint configuration (Collector address)
   - TLS configuration for production
   - Headers for authentication (Bearer token, API key)
   - Timeout settings
4. Batching: SpanExporter batch settings (max_export_batch_size, schedule_delay)
5. Retry: export retry policy (exponential backoff, max retries)
6. Prometheus exporter for metrics:
   - Pull model (Prometheus scrapes) vs push model (OTLP)
   - When to use Prometheus exporter vs OTLP metric exporter
   - Port configuration, path, resource attributes as labels
7. Console exporter: for local development only, never in production
8. Multi-exporter: sending to multiple backends simultaneously (testing migrations)
9. Environment variable configuration vs code configuration
10. Collector-side exporter configuration (OTLP, Prometheus remote write, Loki, Tempo)

Source material context:
- The standards README identifies "operations/exporters/" as a standards domain
- Exporters are part of the operational standards pillar
- Performance requirements for the observability system itself are part of operational standards
  → Include: exporter overhead benchmarks, batch size tuning for throughput
-->
