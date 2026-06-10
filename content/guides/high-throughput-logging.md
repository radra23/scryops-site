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

```csharp
// Scale comparison across different traffic levels
var throughputScenarios = new Dictionary<string, ScenarioMetrics>
{
    ["Small Service"] = new()
    {
        RequestsPerSecond = 100,
        LogsPerRequest = 5,
        LogsPerSecond = 500,
        DailyLogVolume = "43M logs",
        StoragePerDay = "4.3GB",
        ChallengeLevel = "Basic"
    },
    
    ["Medium Service"] = new()
    {
        RequestsPerSecond = 1000,
        LogsPerRequest = 8,
        LogsPerSecond = 8000,
        DailyLogVolume = "691M logs",
        StoragePerDay = "69GB",
        ChallengeLevel = "Moderate"
    },
    
    ["High-Traffic Service"] = new()
    {
        RequestsPerSecond = 10000,
        LogsPerRequest = 12,
        LogsPerSecond = 120000,
        DailyLogVolume = "10.4B logs",
        StoragePerDay = "1TB",
        ChallengeLevel = "Advanced"
    },
    
    ["Internet Scale"] = new()
    {
        RequestsPerSecond = 100000,
        LogsPerRequest = 15,
        LogsPerSecond = 1500000,
        DailyLogVolume = "130B logs",
        StoragePerDay = "13TB",
        ChallengeLevel = "Expert"
    }
};
```

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
                    .AddOtlpExporter(options =>
                    {
                        options.Endpoint = new Uri(configuration["OpenTelemetry:Endpoint"]);
                        options.Protocol = OtlpExportProtocol.Grpc; // More efficient than HTTP
                        
                        // High-throughput batch processing
                        options.BatchExportProcessorOptions = new BatchExportProcessorOptions<LogRecord>
                        {
                            MaxQueueSize = 100000,               // Large queue
                            ScheduledDelayMilliseconds = 100,    // Frequent exports
                            ExporterTimeoutMilliseconds = 10000, // Longer timeout
                            MaxExportBatchSize = 5000           // Large batches
                        };
                    });
            });
        
        return services;
    }
}
```

The right sampling and pipeline design keeps your logs useful at 13TB/day — the wrong defaults make them either incomplete or cost-prohibitive.

- [Your Sampling Strategy Is Lying to You](/guides/sampling-strategy/) — why tail-based sampling is the right model for high-volume systems
- [Distributed Logging](/guides/distributed-logging/) — how logs flow and correlate across service boundaries
- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — the foundational format decisions that make high-throughput pipelines tractable
