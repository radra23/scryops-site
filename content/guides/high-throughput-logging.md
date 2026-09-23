---
title: "High-Throughput Logging: Keeping the Hot Path Fast"
date: 2026-06-07
draft: false
excerpt: "At hundreds of thousands of requests per second, the logging call itself becomes the bottleneck. Async channels, pooling, batching, and circuit breakers keep log I/O off the request thread."
readtime: 9
tags: ["Logs", "Reliability", "Observability"]
series: "High-throughput logging"
series_part: 1
series_title: "Keeping the hot path fast"
---

At 1.5 million log events per second — the rate a 100,000 req/s service produces at 15 log lines per request — synchronous logging stops being an option and becomes a bottleneck. The queue fills, the write thread blocks, and the service pays latency for log I/O. The challenge is not just volume: it is that every architecture decision made at moderate scale (blocking writes, uniform log levels, single-threaded export) hits a hard ceiling at this rate.

When your systems grow from hundreds of requests per second to hundreds of thousands, the changes required go beyond tuning buffer sizes. This guide covers the half that lives inside your process: getting the log call off the request thread and keeping it off, even when a sink fails. Its companion, [Sampling, Collectors, and the Wire](/guides/high-throughput-log-pipelines/), covers what you keep, where you batch, and what it costs to ship.

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

{{< obs-state-machine title="CIRCUIT BREAKER"
      subtitle="// sink failure isolates the pipeline, then recovers"
      caption="Fig. — The breaker trips on failure count, waits out recoveryTime, then risks exactly one probe. A failed probe re-opens it rather than retrying immediately." >}}
{
  "states": [
    {"label":"Closed","caption":"logs flow normally","health":"healthy","entry":true},
    {"label":"Open","caption":"fallback to stderr","health":"failed","trigger":"failure count ≥ threshold"},
    {"label":"HalfOpen","caption":"one probe allowed","health":"probing","trigger":"recoveryTime elapsed"}
  ],
  "returns": [
    {"from":"HalfOpen","to":"Closed","trigger":"probe succeeds — sink is back"},
    {"from":"HalfOpen","to":"Open","trigger":"probe fails — wait another recoveryTime"}
  ]
}
{{< /obs-state-machine >}}

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

## Where to Go Next

- **Prove the premise.** Everything above assumes a channel enqueue is cheaper than a synchronous write under contention. [Benchmark Synchronous vs Channel Logging](/howtos/benchmark-sync-vs-channel-logging/) measures it in .NET, Go, and Python.
- **Decide what to keep and where to batch.** [High-Throughput Logging: Sampling, Collectors, and the Wire](/guides/high-throughput-log-pipelines/) picks up where this guide stops: content-aware sampling, OTel exporter tuning, offloading batching to the Collector, serialization, and compression.
