---
title: "High-Throughput Logging: Scaling Observability to Internet Scale"
date: 2026-06-07
draft: false
excerpt: "When your systems hit hundreds of thousands of requests per second, traditional logging collapses. Here is how to rethink collection, sampling, and export for extreme scale."
readtime: 12
tags: ["Logs", "OpenTelemetry", "Observability", "Sampling"]
---

At 1.5 million log events per second — the rate a 100,000 req/s service produces at 15 log lines per request — synchronous logging stops being an option and becomes a bottleneck. The queue fills, the write thread blocks, and the service pays latency for log I/O. The challenge is not just volume: it is that every architecture decision made at moderate scale (blocking writes, uniform log levels, single-threaded export) hits a hard ceiling at this rate.

When your systems grow from hundreds of requests per second to hundreds of thousands, the changes required go beyond tuning buffer sizes. The exporter protocol, sampling policy, batch cadence, and back-pressure behavior all need explicit redesign for the load.

## The Scale Challenge: When Good Enough Isn't Good Enough

At 50,000 orders per minute across multiple microservices, each generating a dozen or more log lines, you are producing millions of log messages per minute. At that rate, synchronous log writes serialize against I/O, uniform sampling discards the signal you most need, and a single export thread cannot drain the queue fast enough. The result is either dropped logs or cascading latency.

### The Numbers Game

At 1M+ log events per minute, standard synchronous logging exhausts I/O budgets and adds measurable request latency. The table below shows how volume scales with traffic:

| Traffic level | RPS | Logs/request | Logs/second | Daily volume | Storage/day |
|---|---|---|---|---|---|
| Small service | 100 | 5 | 500 | 43M | 4.3 GB |
| Medium service | 1,000 | 8 | 8,000 | 691M | 69 GB |
| High-traffic service | 10,000 | 12 | 120,000 | 10.4B | 1 TB |
| Internet scale | 100,000 | 15 | 1,500,000 | 130B | 13 TB |

{{< obs-throughput-volume >}}

## Building on Async Foundations: The Performance Multiplier

Async logging at standard scale uses a single background writer and a modest queue. At high throughput, that single writer becomes the bottleneck: the queue fills faster than one thread drains it, and you need multiple concurrent consumers, explicit back-pressure signaling, and overflow policies that shed low-priority logs before they cause producer stalls.

### Advanced Async Patterns

```csharp
public class HighThroughputLogger
{
    private readonly Channel<LogEntry> _logChannel;
    private readonly SemaphoreSlim _backpressureSemaphore;
    private readonly ConcurrentBag<Task> _processingTasks;
    private readonly HighThroughputConfig _config;
    
    public HighThroughputLogger(HighThroughputConfig config)
    {
        _config = config;
        
        // Create bounded channel with overflow protection
        var channelOptions = new BoundedChannelOptions(config.ChannelCapacity)
        {
            FullMode = BoundedChannelFullMode.DropOldest, // Preserve recent logs
            SingleReader = false, // Multiple consumer threads
            SingleWriter = false, // Multiple producer threads
            AllowSynchronousContinuations = false // Prevent deadlocks
        };
        
        _logChannel = Channel.CreateBounded<LogEntry>(channelOptions);
        _backpressureSemaphore = new SemaphoreSlim(config.MaxConcurrentOperations);
        _processingTasks = new ConcurrentBag<Task>();
        
        // Start multiple background processing tasks
        StartBackgroundProcessors();
    }
    
    public async ValueTask LogAsync<T>(LogLevel level, string message, T context)
    {
        // Fast path: try to enqueue without blocking
        var logEntry = new LogEntry
        {
            Level = level,
            Message = message,
            Context = context,
            Timestamp = DateTimeOffset.UtcNow,
            ThreadId = Environment.CurrentManagedThreadId,
            TraceId = Activity.Current?.TraceId.ToString()
        };
        
        // Non-blocking enqueue with overflow protection
        if (!_logChannel.Writer.TryWrite(logEntry))
        {
            // Channel is full - apply back-pressure or drop based on policy
            await ApplyBackpressurePolicy(logEntry);
        }
    }
}
```

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

## Object Pooling

At high throughput, `new LogEntry()` per log call generates enough short-lived allocations to sustain GC pressure. Object pooling reuses instances:

```csharp
public class LogEntryPool
{
    private readonly ObjectPool<LogEntry> _pool;

    public LogEntryPool()
    {
        _pool = new DefaultObjectPool<LogEntry>(
            new LogEntryPoolPolicy(),
            maximumRetained: 1000);
    }

    public LogEntry Rent()
    {
        var entry = _pool.Get();
        entry.Reset();  // clear previous data before reuse
        return entry;
    }

    public void Return(LogEntry entry)
    {
        entry.ClearSensitiveData();
        _pool.Return(entry);
    }
}

public class LogEntryPoolPolicy : IPooledObjectPolicy<LogEntry>
{
    public LogEntry Create() => new LogEntry();

    public bool Return(LogEntry obj)
    {
        // Don't pool oversized entries — they hold more memory than the allocation they saved
        return obj.EstimatedSize < 10_000;
    }
}
```

`DefaultObjectPool<T>` is from `Microsoft.Extensions.ObjectPool`. The `maximumRetained` cap prevents the pool from holding more memory than the GC pressure it was meant to reduce.

## Batching and Flush Policy

Writing one log record per I/O call is expensive at volume. Batching groups entries and flushes on count or age, whichever comes first:

```csharp
public class SmartBatchProcessor
{
    private readonly IBatchSink[]  _sinks;
    private readonly BatchingConfig _config;
    private readonly ConcurrentDictionary<string, BatchBuffer> _buffers;

    public SmartBatchProcessor(IBatchSink[] sinks, BatchingConfig config)
    {
        _sinks   = sinks;
        _config  = config;
        _buffers = new ConcurrentDictionary<string, BatchBuffer>();
        _        = Task.Run(FlushBatchesPeriodically);
    }

    public async Task ProcessLogEntry(LogEntry entry)
    {
        var key    = RoutingKey(entry);
        var buffer = _buffers.GetOrAdd(key, _ => new BatchBuffer(_config));
        buffer.Add(entry);
        if (buffer.ShouldFlush())
            await FlushBuffer(key, buffer);
    }

    private static string RoutingKey(LogEntry entry) =>
        entry.Level switch
        {
            LogLevel.Error   => "errors",
            LogLevel.Warning => "warnings",
            _ when entry.IsBusinessEvent  => "business",
            _ when entry.IsPerformanceLog => "performance",
            _                             => "general"
        };
}

public class BatchBuffer
{
    private readonly List<LogEntry> _entries = new();
    private readonly BatchingConfig _config;
    private readonly object  _lock = new();
    private DateTime _firstEntryTime;

    public BatchBuffer(BatchingConfig config) => _config = config;

    public void Add(LogEntry entry)
    {
        lock (_lock)
        {
            if (_entries.Count == 0) _firstEntryTime = DateTime.UtcNow;
            _entries.Add(entry);
        }
    }

    public bool ShouldFlush()
    {
        lock (_lock)
            return _entries.Count >= _config.MaxBatchSize ||
                   DateTime.UtcNow - _firstEntryTime >= _config.MaxBatchAge;
    }

    public LogBatch ExtractBatch()
    {
        lock (_lock)
        {
            var batch = new LogBatch(_entries.ToArray());
            _entries.Clear();
            return batch;
        }
    }
}
```

Flush on count handles sustained load. Flush on age handles bursty patterns where the count threshold might not be reached before the signal goes stale.

### Adaptive Batching Strategies

At extreme load, a single fixed batch size is a compromise: too small at peak, too coarse at idle. Load-aware strategy switching adjusts batch size and flush interval as queue depth climbs:

```csharp
public record BatchingStrategy(
    int      BatchSize,
    TimeSpan FlushInterval,
    int      MaxConcurrentBatches,
    int      BackpressureThreshold);

public enum SystemLoadLevel { LowLoad, Normal, HighLoad, Critical }

public class AdaptiveBatchingConfig
{
    public static readonly Dictionary<SystemLoadLevel, BatchingStrategy> Strategies = new()
    {
        [SystemLoadLevel.LowLoad] = new(
            BatchSize:             50,
            FlushInterval:         TimeSpan.FromMilliseconds(50),
            MaxConcurrentBatches:  2,
            BackpressureThreshold: 1_000),

        [SystemLoadLevel.Normal] = new(
            BatchSize:             100,
            FlushInterval:         TimeSpan.FromMilliseconds(100),
            MaxConcurrentBatches:  4,
            BackpressureThreshold: 5_000),

        [SystemLoadLevel.HighLoad] = new(
            BatchSize:             500,
            FlushInterval:         TimeSpan.FromMilliseconds(200),
            MaxConcurrentBatches:  8,
            BackpressureThreshold: 25_000),

        [SystemLoadLevel.Critical] = new(
            BatchSize:             2_000,
            FlushInterval:         TimeSpan.FromMilliseconds(500),
            MaxConcurrentBatches:  16,
            BackpressureThreshold: 100_000),
    };
}
```

The active `BatchingStrategy` drives `SmartBatchProcessor.BatchingConfig`. Load level is measured by queue depth sampled on a short interval — a rising queue depth signals the need to grow batches before back-pressure reaches the application threads.

## Circuit Breakers

When a downstream log sink becomes unavailable, write attempts queue up and exhaust threads. A circuit breaker stops calling a failing sink after a configurable failure threshold and retries after a recovery window:

```csharp
public class CircuitBreaker
{
    private volatile CircuitBreakerState _state = CircuitBreakerState.Closed;
    private int      _failureCount;
    private DateTime _lastFailureTime;

    private readonly int      _failureThreshold;
    private readonly TimeSpan _recoveryTime;
    private readonly TimeSpan _timeout;
    private readonly object   _lock = new();

    public CircuitBreaker(int failureThreshold, TimeSpan recoveryTime, TimeSpan timeout)
    {
        _failureThreshold = failureThreshold;
        _recoveryTime     = recoveryTime;
        _timeout          = timeout;
    }

    public async Task ExecuteAsync(Func<Task> operation)
    {
        if (_state == CircuitBreakerState.Open)
        {
            if (DateTime.UtcNow - _lastFailureTime < _recoveryTime)
                throw new CircuitBreakerOpenException();

            lock (_lock)
            {
                if (_state == CircuitBreakerState.Open)
                    _state = CircuitBreakerState.HalfOpen;
            }
        }

        try
        {
            using var cts = new CancellationTokenSource(_timeout);
            await operation().ConfigureAwait(false);
            OnSuccess();
        }
        catch
        {
            OnFailure();
            throw;
        }
    }

    private void OnSuccess()
    {
        lock (_lock) { _failureCount = 0; _state = CircuitBreakerState.Closed; }
    }

    private void OnFailure()
    {
        lock (_lock)
        {
            _failureCount++;
            _lastFailureTime = DateTime.UtcNow;
            if (_failureCount >= _failureThreshold)
                _state = CircuitBreakerState.Open;
        }
    }
}

public class ResilientLogProcessor
{
    private readonly ConcurrentDictionary<string, CircuitBreaker> _circuitBreakers = new();
    private readonly IFallbackSink _fallbackSink;

    public ResilientLogProcessor(IFallbackSink fallbackSink)
        => _fallbackSink = fallbackSink;

    public async Task ProcessBatch(LogBatch batch, string sinkName)
    {
        var cb = GetOrCreate(sinkName);
        try
        {
            await cb.ExecuteAsync(() => ProcessBatchInternal(batch, sinkName));
        }
        catch (CircuitBreakerOpenException)
        {
            // Primary sink unavailable — write to fallback (stderr, local file, or secondary Collector)
            await _fallbackSink.WriteBatchAsync(batch);
        }
    }

    // ConcurrentDictionary.GetOrAdd is thread-safe. Under contention the factory
    // may run more than once, but only one CircuitBreaker per sink is ever stored —
    // a plain Dictionary written from many logging threads would corrupt instead.
    private CircuitBreaker GetOrCreate(string sinkName) =>
        _circuitBreakers.GetOrAdd(sinkName, _ => new CircuitBreaker(
            failureThreshold: 5,
            recoveryTime:     TimeSpan.FromMinutes(2),
            timeout:          TimeSpan.FromSeconds(30)));
}
```

The fallback sink should target something that cannot fail — stderr or a local file on disk. The circuit stays open for `recoveryTime`, then admits a probe; on success it closes. One caveat worth knowing: while half-open, the implementation above can let more than one probe through at once — in production you usually single-flight that probe (an `Interlocked` gate) so a sink that is only just recovering is not hit by a burst.

{{< mermaid >}}
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: failure count >= threshold
    Open --> HalfOpen: recoveryTime elapsed
    HalfOpen --> Closed: probe succeeds
    HalfOpen --> Open: probe fails
{{< /mermaid >}}

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

## Common Pitfalls

**The thundering herd.** A sudden load spike fills any fixed-size channel or queue. Without a `BoundedChannelFullMode` policy, writers block; with `DropOldest`, you preserve recency at the cost of the oldest queued entries. Choose `DropOldest` for most observability scenarios — a miss during a spike is acceptable, but a stalled request thread during a spike is not.

**The memory leak trap.** An unbounded accumulation list is the most common failure mode in custom batch processors:

```csharp
// ❌ Never pruned — grows until OOM
public class LeakyProcessor
{
    private readonly List<LogEntry> _all = new();
    public void Process(LogEntry e) => _all.Add(e);
}

// ✅ Bounded queue with periodic pruning
public class ManagedProcessor : IDisposable
{
    private readonly ConcurrentQueue<LogEntry> _queue = new();
    private readonly Timer _cleanup;

    public ManagedProcessor()
    {
        _cleanup = new Timer(_ =>
        {
            var cutoff = DateTime.UtcNow.AddMinutes(-10);
            while (_queue.TryPeek(out var e) && e.Timestamp < cutoff)
                _queue.TryDequeue(out _);
        }, null, TimeSpan.FromMinutes(5), TimeSpan.FromMinutes(5));
    }

    public void Dispose() => _cleanup.Dispose();
}
```

**Configuration explosion.** Adaptive sampling with dozens of per-category rules becomes a maintenance burden. Start with sensible defaults and override only the categories that need it:

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

## Benchmarking the Baseline: Sync vs Channel

Every decision in this guide rests on one claim: synchronous logging makes the calling thread wait for I/O, and a queue or channel takes that wait off the hot path. That is worth measuring rather than asserting — and each language has a native way to do it: [BenchmarkDotNet](https://benchmarkdotnet.org/) in .NET, the `testing` package's parallel benchmarks in Go, and `perf_counter` around `QueueHandler` in Python. Each harness below pits a synchronous, locked write against a queue/channel enqueue under concurrent producers — the regime a high-throughput service actually runs in.

{{< codetabs >}}
```csharp
// requires: BenchmarkDotNet, System.Threading.Channels
[MemoryDiagnoser]
[SimpleJob(warmupCount: 3, iterationCount: 10)]
public class LoggingThroughputBenchmark
{
    private StreamWriter _sink   = null!;
    private readonly object _sinkLock = new();
    private Channel<string> _channel = null!;
    private Task _drain = null!;

    [Params(1, 8, 32)]   // 1, 8, 32 concurrent producer threads
    public int Producers;

    [GlobalSetup]
    public void Setup()
    {
        // A sink that performs a real write+flush, like a file or console
        _sink = new StreamWriter(File.Create(Path.GetTempFileName())) { AutoFlush = true };

        _channel = Channel.CreateBounded<string>(new BoundedChannelOptions(100_000)
        {
            FullMode     = BoundedChannelFullMode.DropOldest,
            SingleReader = true,
            SingleWriter = false
        });
        // One background consumer drains the queue and pays the I/O cost off the hot path
        _drain = Task.Run(async () =>
        {
            await foreach (var line in _channel.Reader.ReadAllAsync())
                _sink.Write(line);
        });
    }

    // Synchronous: the caller serializes AND writes, serialized behind a lock —
    // exactly what a thread-safe synchronous sink does under concurrency.
    [Benchmark(Baseline = true)]
    public void SynchronousWrite() => Parallel.For(0, Producers * 10_000,
        new ParallelOptions { MaxDegreeOfParallelism = Producers },
        _ => { var line = Render(); lock (_sinkLock) _sink.Write(line); });

    // Channel: the caller serializes and enqueues; the drain task absorbs the I/O.
    [Benchmark]
    public void ChannelEnqueue() => Parallel.For(0, Producers * 10_000,
        new ParallelOptions { MaxDegreeOfParallelism = Producers },
        _ => _channel.Writer.TryWrite(Render()));

    private static string Render() =>
        $"{DateTime.UtcNow:O} INFO order processed id={Random.Shared.Next()}";

    [GlobalCleanup]
    public void Cleanup()
    {
        _channel.Writer.Complete();
        _drain.Wait();
        _sink.Dispose();
    }
}
```
```python
# Standard library only. Threads simulate concurrent producers; the GIL bounds
# parallelism, but the queue still moves the write off the calling thread.
import logging, queue, threading, time
from logging.handlers import QueueHandler, QueueListener

THREADS, PER_THREAD = 32, 50_000

def run(setup, label):
    logger = logging.getLogger(label); logger.handlers.clear(); logger.setLevel(logging.INFO)
    listener = setup(logger)
    gate = threading.Barrier(THREADS)               # release all producers together
    def worker():
        gate.wait()
        for i in range(PER_THREAD):
            logger.info("order processed id=%d", i)
    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    t0 = time.perf_counter()
    for t in threads: t.start()
    for t in threads: t.join()
    caller_secs = time.perf_counter() - t0          # time the producers were busy
    if listener: listener.stop()
    print(f"{label:11} {THREADS * PER_THREAD / caller_secs:>11,.0f} msg/s (caller-side)")

def synchronous(logger):                            # caller writes+flushes, behind the handler lock
    logger.addHandler(logging.FileHandler("/dev/null"))
    return None

def channel(logger):                                # caller enqueues; listener drains on its own thread
    q = queue.Queue(maxsize=100_000)
    logger.addHandler(QueueHandler(q))
    listener = QueueListener(q, logging.FileHandler("/dev/null"))
    listener.start()
    return listener

run(synchronous, "synchronous")
run(channel,     "channel")
```
```go
// logging_bench_test.go — run: go test -bench=. -benchmem
package logbench

import (
	"context"
	"io"
	"log/slog"
	"testing"
)

// Synchronous: every caller encodes and writes through the handler, serialized by its mutex.
func BenchmarkSyncLogging(b *testing.B) {
	logger := slog.New(slog.NewJSONHandler(io.Discard, nil))
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			logger.Info("order processed", "id", 42)
		}
	})
}

// Channel-based: the caller hands the record to a buffered channel; a goroutine drains it.
func BenchmarkChannelLogging(b *testing.B) {
	sink := slog.NewJSONHandler(io.Discard, nil)
	ch := make(chan slog.Record, 100_000)
	done := make(chan struct{})
	go func() {
		for rec := range ch {
			_ = sink.Handle(context.Background(), rec) // encode + I/O happen here, off the hot path
		}
		close(done)
	}()

	logger := slog.New(&channelHandler{ch: ch})
	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			logger.Info("order processed", "id", 42)
		}
	})
	b.StopTimer()
	close(ch)
	<-done
}

// channelHandler enqueues records instead of encoding and writing them.
type channelHandler struct{ ch chan slog.Record }

func (h *channelHandler) Enabled(context.Context, slog.Level) bool { return true }
func (h *channelHandler) Handle(_ context.Context, r slog.Record) error {
	select {
	case h.ch <- r: // non-blocking enqueue
	default:        // queue full: drop rather than stall the caller
	}
	return nil
}
func (h *channelHandler) WithAttrs([]slog.Attr) slog.Handler { return h }
func (h *channelHandler) WithGroup(string) slog.Handler      { return h }
```
{{< /codetabs >}}

The absolute numbers depend entirely on your sink and host, so run it for your own — but the *shape* is stable across hardware. A synchronous write makes each caller wait for the serialize and the flush behind a shared lock, so its per-call cost is the sink's I/O latency, and that cost climbs as producers contend for the lock. A bounded-channel `TryWrite` is an in-memory enqueue — tens of nanoseconds uncontended, and even with many writers it stays far below the cost of one I/O flush — so it holds roughly flat as producers scale. Once the sink does real I/O, the per-call gap is frequently two to three orders of magnitude, and it *widens* with concurrency. Python is the asterisk here: the GIL caps raw parallelism, so its throughput gap is narrower than Go's or .NET's — but moving the write off the calling thread still protects request-handling latency, which is the whole point.

Two cautions when you run this. Measure caller latency — the time the request thread is blocked — not just total wall-clock; that blocked time is what your p99 pays. And measure under saturation, not just steady state: the channel's speed comes with a trade-off the synchronous path does not have. Once producers outrun the drain task, `DropOldest` sheds records. The question the benchmark answers is not "which is faster when nothing is contended" but "which one protects the request thread when everything is."

## Serialization and Wire Efficiency

Two costs survive even after logging is asynchronous and batched: turning each record into bytes, and pushing those bytes over the wire. At 1.5M events per second both land in your CPU and egress bills, and both have well-understood fixes.

**Serialize on the fast path, not the reflective one.** Every JSON library ships two gears: a convenient default that inspects each object by reflection (or builds a dict and walks it), and a faster path that skips that work. On a logging hot path you serialize the same handful of record shapes billions of times and never read them back, so the fast path is pure upside. In .NET that is the `System.Text.Json` source generator in write-only mode; in Python, a native-code serializer like `orjson` in place of the stdlib `json` module; in Go, `slog`'s typed attributes instead of reflective `Any` values.

{{< codetabs >}}
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
{{< /codetabs >}}

Whatever the language, three rules carry most of the benefit: reuse the serializer rather than rebuilding it per call, drop null and empty fields so absent data costs zero bytes, and never pretty-print in production — indentation inflates every payload with whitespace you immediately pay to store and ship. Microsoft's guidance is explicit on the .NET case: source generation eliminates runtime reflection, reduces memory, and in write-only mode raises serialization throughput — the only path that also works under Native AOT.

**Compress the OTLP payload.** Telemetry is repetitive JSON — the same keys, levels, and service names on every record — which is exactly what gzip is built for; OTLP log and trace batches routinely compress several-fold. Every SDK exposes it directly:

{{< codetabs >}}
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
{{< /codetabs >}}

The same switch is available without touching code through the `OTEL_EXPORTER_OTLP_COMPRESSION=gzip` environment variable, which all three SDKs honor. The trade is CPU for bytes: gzip spends processor time to shrink what crosses the network, so it pays off most on the egress-billed hop. When the SDK ships to a Collector on `localhost`, the bytes never leave the box — so don't compress there; compress on the Collector's *exporter* instead, on the way to the backend where the network actually costs:

```yaml
# OTel Collector — compress on the expensive hop, not the localhost one
exporters:
  otlphttp/backend:
    endpoint: https://otlp.example.com
    compression: gzip
```

Measure the CPU cost before enabling it everywhere. On a service already CPU-bound at 1.5M events/second, compression competes with request handling; on a network- or egress-bound service it is nearly free savings. The decision is per hop, not global.

The right sampling and pipeline design keeps your logs useful at 13TB/day — the wrong defaults make them either incomplete or cost-prohibitive.

- [Your Sampling Strategy Is Lying to You](/guides/sampling-strategy/) — why tail-based sampling is the right model for high-volume systems
- [Distributed Logging](/guides/distributed-logging/) — how logs flow and correlate across service boundaries
- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — the foundational format decisions that make high-throughput pipelines tractable
