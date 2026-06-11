---
title: "Configuring OTel Exporters: Getting Telemetry from Your Code to Your Backend"
date: 2026-06-10
draft: true
excerpt: "The exporter is the last step in the OTel pipeline — the piece that sends your spans, metrics, and logs to a backend. A guide to configuring OTLP, Prometheus, and Jaeger exporters correctly, with production-ready settings for batching, retry, and authentication."
readtime: 8
tags: ["OpenTelemetry", "Collector", "Observability", "Best Practices"]
---

An exporter is the component that moves telemetry from memory to somewhere useful — a local Collector, a cloud backend, a Prometheus scrape endpoint. It sounds like plumbing, and it is, but misconfigured plumbing is how you lose telemetry under load, accumulate unbounded memory usage, or introduce 100ms of latency on every request from synchronous export.

## The Architecture: SDK → Collector → Backend

The OTel SDK includes exporters that can write directly to a backend — Honeycomb, Datadog, New Relic, Grafana Cloud. Don't use them. Export to a local OTel Collector instead, and let the Collector forward to the backend.

{{< mermaid >}}
graph LR
    A[Your Service] -->|OTLP gRPC :4317| B[OTel Collector]
    B -->|vendor protocol| C[Backend]
    B -->|Prometheus remote_write| D[Metrics store]
    B -->|Loki push| E[Log store]
{{< /mermaid >}}

Why the indirection matters:

**Batching and buffering happen in the Collector, not in your service.** The Collector's `batch` processor aggregates spans before sending them upstream. Your service ships small batches to a local process; the Collector handles the larger, less frequent sends to the backend. This reduces backend API call volume and your service's network overhead.

**Retry lives outside your service.** If the backend is temporarily unavailable, the Collector queues and retries. Your service does not need to handle backend outages — it keeps exporting to the local Collector and the Collector manages the backpressure.

**Vendor switching is a Collector config change, not a code change.** Switching from Datadog to Honeycomb is one line of Collector configuration when your service exports OTLP. If your service exports a vendor-specific format directly, it is a code change across every service.

## OTLP Exporter Configuration

OTLP is the native format. Every OTel-compatible backend accepts it. Configure it once in `Program.cs` for .NET:

```csharp
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing => tracing
        .AddOtlpExporter(opts =>
        {
            opts.Endpoint = new Uri("http://localhost:4317");
            opts.Protocol = OtlpExportProtocol.Grpc;  // default
        }))
    .WithMetrics(metrics => metrics
        .AddOtlpExporter(opts =>
        {
            opts.Endpoint = new Uri("http://localhost:4317");
        }));

builder.Logging.AddOpenTelemetry(logging =>
    logging.AddOtlpExporter(opts =>
    {
        opts.Endpoint = new Uri("http://localhost:4317");
    }));
```

**gRPC (port 4317) vs HTTP (port 4318).** Both carry the same OTLP payload. Use gRPC by default — it is more efficient and supports streaming. Use HTTP when your networking layer does not support HTTP/2 (some older load balancers, API gateways, and service meshes only forward HTTP/1.1).

**For OTLP/HTTP**, set `OtlpExportProtocol.HttpProtobuf` and target port 4318:

```csharp
opts.Endpoint = new Uri("http://localhost:4318/v1/traces");
opts.Protocol = OtlpExportProtocol.HttpProtobuf;
```

**Authentication headers.** When exporting directly to a cloud backend (without a Collector in between), pass API keys as headers:

```csharp
opts.Headers = "x-honeycomb-team=your-api-key,x-honeycomb-dataset=your-dataset";
// Or for Bearer token auth:
opts.Headers = "Authorization=Bearer your-token";
```

**Timeouts.** The default export timeout is 10 seconds. For a local Collector this is far too generous — it means a stuck export holds a span processor thread for 10 seconds. Tighten it for local Collector exports:

```csharp
opts.TimeoutMilliseconds = 3000;
```

## Batching and Queue Configuration

The `BatchSpanProcessor` (the default when you configure an OTLP exporter for traces) holds spans in a queue and exports them in batches. Four settings control its behaviour:

```csharp
.AddOtlpExporter(opts =>
{
    opts.Endpoint = new Uri("http://localhost:4317");
    opts.BatchExportProcessorOptions = new BatchExportProcessorOptions<Activity>
    {
        // How many spans per export batch (default: 512)
        MaxExportBatchSize = 512,
        // How long to wait before flushing (default: 5000ms)
        ScheduledDelayMilliseconds = 5_000,
        // Timeout for a single export attempt (default: 30000ms)
        ExporterTimeoutMilliseconds = 10_000,
        // Max spans held in memory before dropping (default: 2048)
        MaxQueueSize = 2_048,
    };
})
```

**MaxQueueSize is your memory ceiling.** When the queue is full, new spans are dropped. At the default 2048 limit with spans averaging ~2KB each, queue saturation uses about 4MB. Under normal load this queue should be near-empty — saturation indicates the Collector or backend is too slow relative to your service's span emission rate.

**ScheduledDelayMilliseconds controls export latency vs. efficiency.** A shorter delay means spans appear in your backend faster but generates more export calls. The default 5 seconds is appropriate for production. For local development you can drop it to 1 second for more responsive trace visibility.

**Metrics use a push interval, not a queue.** The `PeriodicExportingMetricReader` controls how often metrics are collected and exported:

```csharp
.WithMetrics(metrics => metrics
    .AddOtlpExporter(opts =>
    {
        opts.Endpoint = new Uri("http://localhost:4317");
        opts.MetricReaderOptions = new MetricReaderOptions
        {
            PeriodicExportingMetricReaderOptions =
                new PeriodicExportingMetricReaderOptions
                {
                    ExportIntervalMilliseconds = 60_000,  // default: 60s
                    ExportTimeoutMilliseconds = 30_000,
                }
        };
    }))
```

## The Collector batch Processor

On the Collector side, the `batch` processor aggregates signals before forwarding to the upstream backend. This is where most of the batching value is realised:

```yaml
processors:
  batch:
    # Wait up to 200ms before sending, regardless of size
    timeout: 200ms
    # Send when this many items have accumulated (whichever comes first)
    send_batch_size: 8192
    # Hard cap: never send more than this in a single request (0 = no cap)
    send_batch_max_size: 16384

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/backend]
```

`send_batch_size` is the target; `send_batch_max_size` is the safety cap. Set `send_batch_max_size` to roughly `2 × send_batch_size` to allow for bursts without capping a batch mid-flush.

## Retry and Queue on the Collector

The Collector's OTLP exporter has built-in retry with exponential backoff:

```yaml
exporters:
  otlphttp/backend:
    endpoint: "https://api.honeycombio/v1/traces"
    headers:
      "x-honeycomb-team": "${env:HONEYCOMB_API_KEY}"
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s   # give up after 5 minutes total
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000         # requests in the retry queue
```

`max_elapsed_time` is the circuit breaker. Without it, a prolonged backend outage causes the retry queue to grow indefinitely. Set it to your acceptable "data loss on backend outage" window.

## Prometheus Exporter: Pull vs Push

For metrics specifically, you have a choice: push metrics to the Collector via OTLP (the default pattern above), or expose a pull endpoint that Prometheus scrapes.

Use the **pull model** when:
- You already run Prometheus and want to keep your existing scrape infrastructure
- You need Prometheus-native features (remote_write rules, alert manager integration)
- Your service count is manageable for Prometheus to scrape directly

Use the **push model** (OTLP to Collector) when:
- You are starting fresh and want a single egress point
- Your services are short-lived or ephemeral (Prometheus scrapes may miss them)
- You want metrics and traces to share the same pipeline and routing configuration

The Prometheus pull exporter for .NET requires adding `OpenTelemetry.Exporter.Prometheus.AspNetCore` and registering the endpoint:

```csharp
.WithMetrics(metrics => metrics
    .AddPrometheusExporter())   // exposes /metrics

// In the app pipeline:
app.UseOpenTelemetryPrometheusScrapingEndpoint();
```

This is an either/or choice per metric pipeline configuration — you do not typically run both OTLP and Prometheus exporters for the same signals unless you are migrating between models.

## Environment Variable Configuration

The OTLP exporter reads standard OTel environment variables, so code configuration can be kept to defaults and overridden at deploy time:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer token123"
OTEL_EXPORTER_OTLP_TIMEOUT=10000
OTEL_BSP_MAX_EXPORT_BATCH_SIZE=512
OTEL_BSP_SCHEDULE_DELAY=5000
OTEL_BSP_MAX_QUEUE_SIZE=2048
```

`OTEL_BSP_*` variables control the `BatchSpanProcessor`. This is the recommended approach for Kubernetes deployments: keep the code configuration as a sensible default, override endpoint and auth credentials via environment variables injected by the deployment manifest.

## Development vs Production Settings

| Setting | Development | Production |
|---------|-------------|------------|
| Export endpoint | `http://localhost:4317` (local Collector or Jaeger) | Internal Collector service |
| Export protocol | Either | gRPC unless proxies require HTTP |
| Scheduled delay | 1000ms (faster feedback) | 5000ms |
| Queue size | 512 (low memory) | 2048+ |
| Export timeout | 5000ms | 10000ms |
| Console exporter | Yes (for span inspection) | Never |

The console exporter (`AddConsoleExporter()`) writes spans as JSON to stdout. It is useful for verifying instrumentation during development. Remove it before production — it creates significant log volume and the output is not structured for ingestion by log aggregators.

<!-- TODO: Add section on multi-exporter pattern (fork pipeline to two backends during migration): use Collector fanout exporter, not SDK dual-exporter -->
<!-- TODO: Add section on Collector-side exporter configuration for specific backends: Loki, Tempo, Thanos remote_write -->
<!-- TODO: Add worked examples for Go, Python, Java OTLP exporter configuration -->
