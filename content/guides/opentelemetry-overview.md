---
title: "OpenTelemetry: What It Is and How It Fits Together"
date: 2026-06-11
draft: true
excerpt: "OpenTelemetry is a single instrumentation layer that produces traces, metrics, and logs in a vendor-neutral format. This guide explains what each signal is for, how the SDK and Collector relate, and where to go next."
readtime: 8
tags: ["OpenTelemetry", "Observability", "Tracing", "Metrics", "Logs"]
---

OpenTelemetry is a CNCF project that standardises how applications produce and export telemetry. Before it existed, every observability vendor required its own SDK, its own agent, and its own wire format. Switching backends meant reinstrumenting the application. Teams running more than one tool maintained multiple pipelines for the same data.

OTel collapses that to one instrumentation layer. You add the SDK once. It emits OTLP — the OpenTelemetry Protocol — a vendor-neutral wire format that every major observability backend now accepts. The choice of backend becomes an operational decision rather than a code change.

## The Three Signals

OTel defines three telemetry signal types. Each answers a different class of question.

**Traces** answer "what happened to this request?" A trace is a directed acyclic graph of spans — one span per unit of work — recording when each operation started, how long it took, whether it succeeded, and what attributes it carried. Distributed tracing links spans across service boundaries using propagated context headers, so a single trace can span an API gateway, three microservices, a message queue consumer, and a database call. Traces are the signal for understanding request paths and diagnosing latency.

{{< obs-trace-waterfall >}}

**Metrics** answer "how is the system behaving right now?" Metrics are numeric measurements aggregated over time: counters that only increase, gauges that represent a current value, and histograms that record distributions. Where a trace tells you that one request took 800ms, a metric tells you that p95 latency has been above 600ms for the last five minutes. Metrics are the signal for alerting and capacity planning.

**Logs** answer "what happened and in what context?" Logs are time-stamped records of discrete events. When correlated with traces via a shared `trace_id`, they provide the narrative detail — error messages, business context, state transitions — that explains what a trace reveals about timing. Logs are the signal for root cause analysis.

The three signals are complementary. An alert fires on a metric; the metric points to a time range; correlated traces show which requests degraded; correlated logs explain why.

## How the Pieces Fit Together

{{< mermaid caption="Fig. — The SDK's three providers emit OTLP to the Collector, which processes it through receivers, processors, and exporters before routing each signal to its own backend." >}}
flowchart TD
    subgraph app ["Your Application"]
        TP[TracerProvider]
        MP[MeterProvider]
        LP[LoggerProvider]
    end

    app -->|OTLP gRPC / HTTP| col

    subgraph col ["OTel Collector"]
        R[Receivers]
        P[Processors\nbatch · filter · transform · sample]
        E[Exporters]
        R --> P --> E
    end

    E -->|OTLP| B1[Tempo / Jaeger]
    E -->|OTLP / remote_write| B2[Prometheus / Mimir]
    E -->|OTLP| B3[Loki / OpenSearch]
{{< /mermaid >}}

**The SDK** lives in your application. Each language has its own implementation — Go, Java, Python, .NET, Node.js, and others — but the APIs are consistent across all of them. The SDK provides `TracerProvider`, `MeterProvider`, and `LoggerProvider`; your instrumentation code uses those to create spans, record measurements, and emit log records. Automatic instrumentation libraries for common frameworks (HTTP servers, database drivers, message brokers) hook into these providers without requiring changes to application code.

**The Collector** is a standalone proxy that sits between your services and your backends. It receives telemetry over OTLP (or a range of other protocols — Jaeger, Prometheus, Zipkin, and more — though Jaeger itself now speaks OTLP natively, so the dedicated `jaegerreceiver` is increasingly optional rather than the primary ingestion path), applies a processing pipeline, and exports to one or more destinations. The Collector handles concerns that don't belong in the application SDK: batching, sampling decisions at the trace level, attribute redaction for PII, fanout to multiple backends, and protocol translation. Running without a Collector is possible for simple setups; at any meaningful scale, the Collector is the right architectural boundary.

**Backends** are the storage and query layers — Grafana Tempo for traces, Prometheus or Mimir for metrics, Loki or OpenSearch for logs. OTel is backend-agnostic; the Collector's exporter configuration is the only place vendor specifics appear.

{{< insight >}}
The SDK and the Collector are independent deployment decisions. You can start by exporting directly from the SDK to a backend and introduce the Collector later — without changing your instrumentation code. The OTLP endpoint just points somewhere else.
{{< /insight >}}

## Resource Attributes: The Identity Layer

Every piece of telemetry produced by your application carries a **resource** — a set of attributes describing the entity that produced it. At minimum: service name, service version, and deployment environment. These attributes appear on every span, metric, and log record the service emits, and they are what makes cross-signal correlation possible in the backend.

```yaml
# Collector resource processor — applied to all signals
processors:
  resource:
    attributes:
      - key: service.name
        value: checkout-api
        action: upsert
      - key: deployment.environment
        value: production
        action: upsert
```

Resource attributes are defined by OTel [semantic conventions](/guides/otel-semantic-conventions/) — a shared vocabulary that makes the same field names mean the same thing across every service and every language SDK.

## Where to Go Next

**By signal:**
- [OTel Metrics Instrumentation](/guides/otel-metrics-instrumentation/) — the six instrument types and when to use each
- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — what schema-consistent logs unlock for automated analysis

**By concept:**
- [Context Propagation](/guides/otel-context-propagation/) — how trace context crosses service boundaries
- [Resource Attributes and Service Naming](/guides/otel-resource-attributes-and-service-naming/) — the identity layer for all three signals
- [Semantic Conventions](/guides/otel-semantic-conventions/) — the standard attribute vocabulary
- [Exporter Configuration](/guides/otel-exporter-configuration/) — wiring the SDK and Collector to your backend
- [SDK Direct vs Collector](/qa/otel-collector-vs-sdk-direct/) — when to use each

**By language (how-tos):**
- [Instrument a .NET Service](/howtos/instrument-dotnet-service-opentelemetry/)
- [Instrument a Python Service](/howtos/instrument-python-service-opentelemetry/)
- [Instrument a Java Service](/howtos/instrument-java-service-opentelemetry/)
- [Instrument a Go Service](/howtos/instrument-go-service-opentelemetry/)
- [Instrument a Node.js Service](/howtos/instrument-nodejs-service-opentelemetry/)

**Migrating from a proprietary SDK:**
- [OTel Migration from Proprietary Tooling](/guides/otel-migration-from-proprietary/)
