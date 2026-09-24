---
title: "High-Throughput Logging: Sampling, Collectors, and the Wire"
date: 2026-06-07
lastmod: 2026-09-23
draft: false
excerpt: "At 1.5 million log events per second you cannot keep, batch, or ship everything the way you did at moderate scale. Content-aware sampling, OTel exporter tuning, Collector-side batching, and cheaper bytes on the wire."
readtime: 11
tags: ["Logs", "Sampling", "OpenTelemetry", "Collector", "OTLP"]
series: "High-throughput logging"
series_part: 2
series_title: "Sampling, Collectors, and the wire"
---

A fast hot path only moves the problem downstream. Once the log call is an in-memory enqueue ([Keeping the Hot Path Fast](/guides/high-throughput-logging/) covers that half), 1.5 million events per second still have to be filtered, batched, serialized, and shipped — and every one of those steps has a default that was tuned for moderate scale. The exporter protocol, sampling policy, batch cadence, and wire format all need explicit redesign for the load.

This guide takes them in the order a record meets them: what to keep, how the SDK exports it, where the batching should live, what it costs on the wire, and how you watch the pipeline itself.

## Intelligent Sampling: Quality Over Quantity

At extreme scale, you can't log everything without overwhelming your infrastructure.

### Adaptive Sampling Strategies

```csharp
public class IntelligentSampler
{
    private readonly Dictionary<string, SamplingStrategy> _strategies;
    
    private Dictionary<string, SamplingStrategy> InitializeSamplingStrategies()
    {
        return new Dictionary<string, SamplingStrategy>
        {
            // Always sample errors and warnings
            ["ERROR"] = new SamplingStrategy { Rate = 1.0, Reason = "Critical for debugging" },
            ["WARN"] = new SamplingStrategy { Rate = 1.0, Reason = "Important for monitoring" },
            
            // Sample INFO based on service load
            ["INFO"] = new SamplingStrategy { Rate = 0.1, Reason = "High volume, adaptive sampling" },
            
            // Heavily sample DEBUG in production
            ["DEBUG"] = new SamplingStrategy { Rate = 0.01, Reason = "Very high volume" },
            
            // Special handling for business events
            ["BUSINESS_EVENT"] = new SamplingStrategy { Rate = 1.0, Reason = "Business critical" },
            
            // Performance logs - sample based on duration
            ["PERFORMANCE"] = new SamplingStrategy { Rate = 0.05, Reason = "High volume monitoring" }
        };
    }
    
    public bool ShouldSample(LogEntry entry)
    {
        var strategy = GetSamplingStrategy(entry);
        
        // Always sample certain conditions
        if (ShouldAlwaysSample(entry))
        {
            return true;
        }
        
        // Apply probabilistic sampling
        var random = Random.Shared.NextDouble();
        return random < strategy.Rate;
    }
    
    private bool ShouldAlwaysSample(LogEntry entry)
    {
        return entry.Level >= LogLevel.Warning ||
               entry.IsBusinessCritical ||
               entry.HasErrorContext ||
               entry.Duration > TimeSpan.FromSeconds(5) ||
               entry.IsFirstOccurrence ||
               entry.HasUserImpact;
    }
}
```

## Content-Aware Sampling

A single probabilistic rate for all `INFO` logs discards payment confirmations at the same rate as health-check responses. Content-aware sampling applies the right rate to the right signal:

```csharp
public class ContentAwareSampler
{
    public SamplingDecision DecideSampling(LogEntry entry)
    {
        return entry.Category switch
        {
            "user_auth"    => new SamplingDecision(1.0,   "Security critical"),
            "payment"      => new SamplingDecision(1.0,   "Business critical"),
            "health_check" => new SamplingDecision(0.001, "Routine monitoring"),

            // Database: always capture slow queries; heavily sample fast ones
            "database" => entry.Duration > TimeSpan.FromMilliseconds(100)
                ? new SamplingDecision(1.0,  "Slow query — always sample")
                : new SamplingDecision(0.01, "Fast query — minimal sample"),

            // HTTP: errors surface fully; 2xx success is sampled down
            "http_request" => SampleByStatusCode(entry),

            _ => new SamplingDecision(0.1, "Default")
        };
    }

    private SamplingDecision SampleByStatusCode(LogEntry entry)
    {
        return entry.GetStatusCode() switch
        {
            >= 500 => new(1.0,  "Server errors always sampled"),
            >= 400 => new(0.5,  "Client errors partially sampled"),
            >= 300 => new(0.1,  "Redirects lightly sampled"),
            _      => new(0.05, "Success responses minimally sampled")
        };
    }
}
```

### Keep the Rule Set Small

Adaptive sampling with dozens of per-category rules becomes a maintenance burden. Start with sensible defaults and override only the categories that need it:

```csharp
public class HighThroughputConfig
{
    public int      MaxLogsPerSecond   { get; set; } = 100_000;
    public TimeSpan BatchFlushInterval { get; set; } = TimeSpan.FromMilliseconds(100);
    public int      MaxBatchSize       { get; set; } = 1_000;
    public double   DefaultSampleRate  { get; set; } = 0.1;

    public static HighThroughputConfig ForEnvironment(string env) =>
        env.ToLowerInvariant() switch
        {
            "production" => ProductionDefaults(),
            "staging"    => StagingDefaults(),
            _            => DevelopmentDefaults()
        };
}
```

## OpenTelemetry Integration: Scale-Aware Configuration

OpenTelemetry configuration needs special tuning for high-throughput scenarios:

```csharp
public static class HighThroughputOpenTelemetryConfig
{
    public static IServiceCollection AddHighThroughputLogging(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        services.AddOpenTelemetry()
            .WithLogging(builder =>
            {
                builder
                    // Two-parameter overload configures both the exporter and the batch processor
                    // Requires OpenTelemetry.Exporter.OpenTelemetryProtocol 1.7+
                    .AddOtlpExporter((exporterOptions, processorOptions) =>
                    {
                        exporterOptions.Endpoint = new Uri(configuration["OpenTelemetry:Endpoint"]);
                        exporterOptions.Protocol = OtlpExportProtocol.Grpc; // gRPC is more efficient than HTTP/JSON at volume

                        // Tune batch processor for high throughput
                        var batch = processorOptions.BatchExportProcessorOptions;
                        batch.MaxQueueSize                = 100_000; // in-memory entries before drop
                        batch.ScheduledDelayMilliseconds  = 100;     // flush every 100ms
                        batch.ExporterTimeoutMilliseconds = 10_000;  // per-batch timeout
                        batch.MaxExportBatchSize          = 5_000;   // entries per OTLP request
                    });
            });
        
        return services;
    }
}
```

## OTel Processor Pattern

For fine-grained control over records before export, implement `BaseProcessor<LogRecord>`. The bounded channel decouples the hot path from any downstream processing latency:

```csharp
public class HighThroughputProcessor : BaseProcessor<LogRecord>
{
    private readonly Channel<LogRecord> _channel;
    private readonly Task _processingTask;

    public HighThroughputProcessor()
    {
        _channel = Channel.CreateBounded<LogRecord>(new BoundedChannelOptions(50_000)
        {
            FullMode     = BoundedChannelFullMode.DropOldest,
            SingleReader = true,
            SingleWriter = false
        });
        _processingTask = Task.Run(ProcessAsync);
    }

    public override void OnEnd(LogRecord logRecord)
    {
        // Non-blocking — drops when full rather than stalling the request thread
        _channel.Writer.TryWrite(logRecord);
    }

    private async Task ProcessAsync()
    {
        await foreach (var record in _channel.Reader.ReadAllAsync())
        {
            // Enrichment or attribute filtering goes here.
            // Note: LogRecord.Attributes and FormattedMessage are read-only.
            // Pass additional context via Activity tags or OTel resource attributes.
        }
    }
}
```

## Offloading Batching to the Collector

At very high throughput — sustained above roughly 5,000 log records per second — in-process batching starts fighting your application's GC. The buffers that smooth out bursts are large byte arrays sitting in the managed heap. They survive Gen 0 and Gen 1 collections, graduate to Gen 2, and contribute to the pause times you were trying to avoid in the first place.

The fix is to stop batching inside the application and let the OTel Collector do it instead. The SDK sends small, frequent OTLP deliveries to a Collector running on localhost. The Collector accumulates those deliveries and emits large, efficient batches toward the backend. The application's buffer shrinks dramatically; the Collector — a separate process with its own memory — absorbs the burst.

Configure the SDK to minimise in-process holding time:

```csharp
builder.Logging.AddOpenTelemetry(options =>
{
    options.AddOtlpExporter((otlpOptions, processorOptions) =>
    {
        otlpOptions.Endpoint = new Uri("http://localhost:4317");
        otlpOptions.Protocol  = OtlpExportProtocol.Grpc;

        // Small, frequent deliveries to the local Collector
        var batch = processorOptions.BatchExportProcessorOptions;
        batch.MaxExportBatchSize         = 200;
        batch.ScheduledDelayMilliseconds = 50;
        batch.MaxQueueSize               = 2_048;
    });
});
```

And let the Collector's `batch` processor do the heavy accumulation before forwarding:

```yaml
# OTel Collector config.yaml
processors:
  batch:
    send_batch_size: 8_192       # Target batch size for the backend exporter
    send_batch_max_size: 10_000  # Hard ceiling per batch
    timeout: 200ms               # Maximum wait before sending an incomplete batch

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/backend]
```

The net effect: the application holds at most ~2,000 records in its in-process queue at any moment; the Collector holds the rest. A Gen 2 collection in your application no longer contends with multi-megabyte log buffers. The Collector can also be shared across multiple services on the same host, which amortises its footprint further.

This architecture shift is worth making when you can measure GC pause contributions from logging buffers in profiling output. If your Channel queue stays well below its bound and GC pressure is low, the in-process approach is simpler — the Collector adds an operational dependency that the SDK-only path avoids.

## Serialization and Wire Efficiency

Two costs survive even after logging is asynchronous and batched: turning each record into bytes, and pushing those bytes over the wire. At 1.5M events per second both land in your CPU and egress bills, and both have well-understood fixes.

**Serialize on the fast path, not the reflective one.** Every JSON library ships two gears: a convenient default that inspects each object by reflection (or builds a dict and walks it), and a faster path that skips that work. On a logging hot path you serialize the same handful of record shapes billions of times and never read them back, so the fast path is pure upside. In .NET that is the `System.Text.Json` source generator in write-only mode; in Python, a native-code serializer like `orjson` in place of the stdlib `json` module; in Go, `slog`'s typed attributes instead of reflective `Any` values.

{{< langswitch >}}
```csharp
using System.Text.Json;
using System.Text.Json.Serialization;

[JsonSourceGenerationOptions(
    GenerationMode         = JsonSourceGenerationMode.Serialization,  // fast path: write-only, highest throughput
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(LogEntry))]
internal partial class LogJsonContext : JsonSerializerContext { }

// Generated, strongly-typed metadata — no reflection, no per-call options object
static byte[] Serialize(LogEntry e) =>
    JsonSerializer.SerializeToUtf8Bytes(e, LogJsonContext.Default.LogEntry);
```
```python
# pip install orjson — a native (Rust) serializer, several times faster than stdlib json
import logging, orjson

class OrjsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return orjson.dumps({
            "ts":     record.created,
            "level":  record.levelname,
            "msg":    record.getMessage(),
            "logger": record.name,
        }).decode()   # orjson handles datetime / UUID / dataclass natively — no custom default

handler = logging.FileHandler("app.log")
handler.setFormatter(OrjsonFormatter())
```
```go
// slog's typed attributes resolve by Kind — no reflection, no fmt on the hot path.
logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

// FAST: typed constructors, zero reflection
logger.LogAttrs(context.Background(), slog.LevelInfo, "order processed",
	slog.String("service", "checkout"),
	slog.Int("order_id", id),
	slog.Duration("took", elapsed),
)

// SLOW: Any falls back to reflection; Sprintf allocates a string the handler re-parses
logger.Info("order processed", slog.Any("order", order), "line", fmt.Sprintf("id=%d", id))
```
{{< /langswitch >}}

Whatever the language, three rules carry most of the benefit: reuse the serializer rather than rebuilding it per call, drop null and empty fields so absent data costs zero bytes, and never pretty-print in production — indentation inflates every payload with whitespace you immediately pay to store and ship. Microsoft's guidance is explicit on the .NET case: source generation eliminates runtime reflection, reduces memory, and in write-only mode raises serialization throughput — the only path that also works under Native AOT.

**Compress the OTLP payload.** Telemetry is repetitive JSON — the same keys, levels, and service names on every record — which is exactly what gzip is built for; OTLP log and trace batches routinely compress several-fold. Every SDK exposes it directly:

{{< langswitch >}}
```csharp
builder.Logging.AddOpenTelemetry(o =>
{
    o.AddOtlpExporter((otlp, processor) =>
    {
        otlp.Endpoint    = new Uri("http://localhost:4317");
        otlp.Protocol    = OtlpExportProtocol.Grpc;
        otlp.Compression = OtlpExportCompression.GZip;   // gzip the batch before it leaves the process
    });
});
```
```python
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from grpc import Compression

exporter = OTLPLogExporter(
    endpoint="localhost:4317",
    insecure=True,
    compression=Compression.Gzip,        # gzip the batch before it leaves the process
)
processor = BatchLogRecordProcessor(exporter)
```
```go
import (
	"context"

	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	"go.opentelemetry.io/otel/sdk/log"
)

exp, err := otlploggrpc.New(context.Background(),
	otlploggrpc.WithEndpoint("localhost:4317"),
	otlploggrpc.WithInsecure(),
	otlploggrpc.WithCompressor("gzip"),    // gzip the batch before it leaves the process
)
if err != nil {
	panic(err)
}
processor := log.NewBatchProcessor(exp)
```
{{< /langswitch >}}

The same switch is available without touching code through the `OTEL_EXPORTER_OTLP_COMPRESSION=gzip` environment variable, which all three SDKs honor. The trade is CPU for bytes: gzip spends processor time to shrink what crosses the network, so it pays off most on the egress-billed hop. When the SDK ships to a Collector on `localhost`, the bytes never leave the box — so don't compress there; compress on the Collector's *exporter* instead, on the way to the backend where the network actually costs:

```yaml
# OTel Collector — compress on the expensive hop, not the localhost one
exporters:
  otlphttp/backend:
    endpoint: https://otlp.example.com
    compression: gzip
```

Measure the CPU cost before enabling it everywhere. On a service already CPU-bound at 1.5M events/second, compression competes with request handling; on a network- or egress-bound service it is nearly free savings. The decision is per hop, not global.

## Pipeline Observability

The logging pipeline itself needs observability. A `Meter` backed by OTel metrics lets you see queue depth, drop rate, and end-to-end latency without adding I/O to the hot path:

```csharp
public class LoggingPipelineMetrics
{
    // Meter is instantiated directly; the OTel SDK collects from all Meter instances
    // registered via builder.WithMetrics(b => b.AddMeter("logging.pipeline"))
    private readonly Meter _meter = new("logging.pipeline", "1.0.0");

    private readonly Counter<long>       _eventsProcessed;
    private readonly Histogram<double>   _processingLatencyMs;
    private readonly UpDownCounter<long> _queueDepth;
    private readonly Counter<long>       _eventsDropped;
    private readonly Counter<long>       _circuitBreakerTrips;

    public LoggingPipelineMetrics()
    {
        _eventsProcessed    = _meter.CreateCounter<long>(
            "logging.events.processed",
            description: "Events successfully processed by the pipeline");

        _processingLatencyMs = _meter.CreateHistogram<double>(
            "logging.processing.latency",
            unit: "ms",
            description: "End-to-end latency from log call to export");

        _queueDepth          = _meter.CreateUpDownCounter<long>(
            "logging.queue.depth",
            description: "Current entries in the logging queue");

        _eventsDropped       = _meter.CreateCounter<long>(
            "logging.events.dropped",
            description: "Events dropped due to back-pressure or circuit breaker");

        _circuitBreakerTrips = _meter.CreateCounter<long>(
            "logging.circuit_breaker.trips",
            description: "Circuit breaker open transitions");
    }

    public void RecordEventProcessed(string level, string destination, bool success, double latencyMs)
    {
        var tags = new TagList();
        tags.Add("level",       level);
        tags.Add("destination", destination);
        tags.Add("status",      success ? "success" : "failure");

        _eventsProcessed.Add(1, tags);
        _processingLatencyMs.Record(latencyMs, tags);
    }

    public void RecordBatchProcessed(int count, string destination, double latencyMs)
    {
        var tags = new TagList();
        tags.Add("destination", destination);
        _eventsProcessed.Add(count, tags);
        _processingLatencyMs.Record(latencyMs, tags);
    }

    public void RecordQueueChange(long delta) =>
        _queueDepth.Add(delta);

    public void RecordDropped(string reason) =>
        _eventsDropped.Add(1, new TagList { { "reason", reason } });

    public void RecordCircuitBreakerTrip(string sink) =>
        _circuitBreakerTrips.Add(1, new TagList { { "sink", sink } });
}
```

Register the meter name in your OTel setup alongside the logging exporter:

```csharp
services.AddOpenTelemetry()
    .WithMetrics(b => b
        .AddMeter("logging.pipeline")
        .AddOtlpExporter());
```

`logging.queue.depth` is the most actionable signal: a sustained climb means the pipeline is not draining fast enough and back-pressure is imminent. Alert on queue depth before alerting on drop rate — depth leads, drops lag.

The right sampling and pipeline design keeps your logs useful at 13TB/day — the wrong defaults make them either incomplete or cost-prohibitive.

## Related

- [High-Throughput Logging: Keeping the Hot Path Fast](/guides/high-throughput-logging/) — async channels, pooling, batching, and circuit breakers inside the process
- [Benchmark Synchronous vs Channel Logging](/howtos/benchmark-sync-vs-channel-logging/) — measure the hot-path claim on your own hardware
