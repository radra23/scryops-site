---
title: "High-Throughput Logging: Scaling Observability to Internet Scale"
date: 2026-06-07
draft: true
excerpt: "When your systems hit hundreds of thousands of requests per second, traditional logging collapses. Here is how to rethink collection, sampling, and export for extreme scale."
readtime: 8
tags: ["Logs", "OpenTelemetry", "Observability", "Sampling"]
---

# High-Throughput Logging: Scaling Observability to Internet Scale

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
    private readonly Dictionary<string, CircuitBreaker> _circuitBreakers = new();
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

    private CircuitBreaker GetOrCreate(string sinkName)
    {
        if (!_circuitBreakers.TryGetValue(sinkName, out var cb))
        {
            cb = new CircuitBreaker(
                failureThreshold: 5,
                recoveryTime:     TimeSpan.FromMinutes(2),
                timeout:          TimeSpan.FromSeconds(30));
            _circuitBreakers[sinkName] = cb;
        }
        return cb;
    }
}
```

The fallback sink should target something that cannot fail — stderr or a local file on disk. The circuit stays open for `recoveryTime` before sending one probe; on success it closes.

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

<!-- TODO: Add BenchmarkDotNet baseline measurements comparing sync vs Channel-based logging under sustained load -->
<!-- TODO: Cover OTel Collector batch processor as the preferred alternative to in-process batching at very high scale (reduces GC impact by moving buffering out of the application process) -->
<!-- TODO: Add serialization optimization section (System.Text.Json options, GZip compression for OTLP payloads) -->

The right sampling and pipeline design keeps your logs useful at 13TB/day — the wrong defaults make them either incomplete or cost-prohibitive.

- [Your Sampling Strategy Is Lying to You](/guides/sampling-strategy/) — why tail-based sampling is the right model for high-volume systems
- [Distributed Logging](/guides/distributed-logging/) — how logs flow and correlate across service boundaries
- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — the foundational format decisions that make high-throughput pipelines tractable
