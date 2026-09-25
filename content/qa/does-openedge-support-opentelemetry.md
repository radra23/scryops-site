---
title: "Does Progress OpenEdge support OpenTelemetry?"
date: 2026-06-15
draft: true
excerpt: "Yes — since OpenEdge 12.6 for metrics and 12.8 for traces, via the OpenEdge Command Center agent and an OTel Collector. There is no native APM agent for OpenEdge; the Collector is the correct integration path to any modern observability backend."
readtime: 3
tags: ["OpenTelemetry", "Observability", "Monitoring", "Operations"]
---

Yes, but only through the OpenEdge Command Center (OECC) agent pipeline — not through an in-process SDK or a native APM agent. There is no dedicated New Relic, Datadog, or Dynatrace agent for OpenEdge ABL applications. The OTel Collector is the official integration path to any modern observability backend.

## What's supported, and since when

**OpenEdge 12.6** introduced OTel metrics support in OECC 1.2. The OECC agent collects performance metrics from PAS for OpenEdge (PASOE) instances and OpenEdge databases and forwards them via OTLP/gRPC to an OTel Collector.

**OpenEdge 12.8** extended this to include **traces** — adding span-level visibility into ABL application code paths for identifying performance bottlenecks without manual instrumentation.

Before 12.6, OTel support doesn't exist. Teams running older versions are limited to infrastructure monitoring (OS-level metrics), custom metrics via APIs, and log forwarding.

## What signals are available

For PASOE instances (via `otagentpasoe.yaml`):
- Agent metrics — worker agent counts, utilisation, queue depth
- Request metrics — request counts, durations, error rates per ABL application
- Session metrics — active sessions, connection counts
- Connection metrics — database connection pool utilisation
- Transport metrics — per-protocol request counts for REST, SOAP, and APSV endpoints

For OpenEdge databases (via `otagentoedb.yaml`):
- Database performance metrics — I/O, locking, buffer utilisation

Trace data (12.8+) covers ABL application execution paths, enabling call-depth analysis that metrics alone can't provide.

## How the pipeline works

The OECC agent reads two YAML configuration files and emits OTLP/gRPC telemetry to an OTel Collector:

```
OpenEdge PASOE / DB
        │
        ▼
  OECC Agent
  ├─ otagentpasoe.yaml   ← configures PASOE metrics collection
  └─ otagentoedb.yaml    ← configures database metrics collection
        │ OTLP/gRPC
        ▼
  OTel Collector (certified: v0.31 – v0.129.1)
        │
        ▼
  APM backend (New Relic, Datadog, Elastic, Dynatrace, Grafana, ...)
```

A minimal Collector `config.yaml` for OpenEdge telemetry:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: localhost:4317   # Must match otagentpasoe/oedb exporter.endpoint

processors:
  batch:

exporters:
  otlphttp/backend:             # Replace with your backend's OTLP endpoint
    endpoint: https://otlp.nr-data.net  # New Relic example
    headers:
      api-key: "${env:NEW_RELIC_LICENSE_KEY}"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/backend]
    traces:                       # 12.8+ only
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/backend]
```

The OECC agent can be installed on a separate host from the Collector; Progress recommends this for production deployments. Multiple OECC agents can share a single Collector.

## What you don't get

OTel support in OpenEdge is infrastructure-level telemetry managed by the OECC agent. You cannot — without significant custom work — instrument individual ABL procedures with custom spans or add business-context attributes (customer ID, transaction type) to traces the way you would with an OTel SDK in a conventional language. The telemetry reflects platform behaviour, not application business logic.

For ABL code running on older versions (pre-12.6), the options are limited: OpenEdge's own logging facility (`OUTPUT TO`, `LOG-MANAGER`) can write structured text that a Collector log receiver can ingest, but this is log forwarding, not native OTel.

## Further reading

- [Progress OpenEdge Command Center documentation — Set up OpenTelemetry Collector](https://docs.progress.com/bundle/openedge-command-center-olh/page/Set-up-OpenTelemetry-Collector.html)
- [Monitor ABL applications using OpenTelemetry](https://docs.progress.com/bundle/openedge-abl-troubleshoot-applications/page/Monitor-ABL-applications-using-OpenTelemetry.html)
- [OTel Collector Configuration](/guides/otel-exporter-configuration/) — configuring the Collector exporters for specific backends
