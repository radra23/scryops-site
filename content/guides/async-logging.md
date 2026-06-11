---
title: "Async Logging: Keeping Your Application Threads Free"
date: 2026-06-11
draft: true
excerpt: "Every synchronous log write forces a request thread to wait on disk or network I/O. Async logging moves that work to background threads so your application threads stay free — here is how to configure it correctly with Serilog and OpenTelemetry."
readtime: 7
tags: ["Logs", "Observability", "OpenTelemetry", "Structured Logging"]
---

Synchronous logging is a hidden tax on request latency. A log write to a rolling file or a remote endpoint involves I/O — disk seeks, network round-trips, format serialisation — and every one of those operations runs on the thread that called `LogInformation`. At low request rates the cost is negligible. At high rates, each log statement becomes a serialisation point that limits throughput.

Async logging separates the act of submitting a log record from the act of delivering it. The application thread enqueues the record into a memory buffer and returns immediately; a dedicated background thread drains the buffer and handles the I/O. The application continues without waiting.

## Serilog: WriteTo.Async()

Serilog provides async wrapping out of the box through `Serilog.Sinks.Async`. Any sink — file, console, OpenTelemetry — can be made async by wrapping it:

```csharp
public static class AsyncLoggingConfiguration
{
    public static IServiceCollection AddAsyncLogging(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        Log.Logger = new LoggerConfiguration()
            .ReadFrom.Configuration(configuration)
            .Enrich.FromLogContext()
            .Enrich.WithThreadId()        // Serilog.Enrichers.Thread
            .Enrich.WithEnvironmentName() // Serilog.Enrichers.Environment

            // Console: small buffer, fast drain
            .WriteTo.Async(a => a.Console(new JsonFormatter()),
                bufferSize: 1000,
                blockWhenFull: false)

            // Rolling file: larger buffer for slower disk writes
            .WriteTo.Async(a => a.File(
                path: configuration["Logging:FilePath"]!,
                formatter: new JsonFormatter(),
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 7),
                bufferSize: 10000,
                blockWhenFull: false)

            // OpenTelemetry export: largest buffer for network latency
            // (Serilog.Sinks.OpenTelemetry — batching handled by the Async wrapper)
            .WriteTo.Async(a => a.OpenTelemetry(options =>
                {
                    options.Endpoint = configuration["OpenTelemetry:Endpoint"];
                    options.Protocol  = OtlpProtocol.GrpcProtobuf;
                }),
                bufferSize: 10000,
                blockWhenFull: false)

            .CreateLogger();

        services.AddLogging(builder =>
        {
            builder.ClearProviders();
            builder.AddSerilog();
        });

        return services;
    }
}
```

### bufferSize and blockWhenFull

These two parameters control what happens when the background thread cannot drain the queue as fast as records arrive:

**`bufferSize`** is the maximum number of log records held in memory before the overflow policy kicks in. Start with the values shown above and adjust based on observed queue depth. A buffer that never fills is fine; a buffer that regularly fills indicates either too-small a buffer or a genuinely overwhelmed sink.

**`blockWhenFull: false`** drops the oldest records when the buffer is full, rather than blocking the application thread. For most sinks this is the right choice — a brief gap in log coverage during a traffic spike is far less harmful than the request latency that blocking would introduce. Use `blockWhenFull: true` only for sinks where log loss is genuinely unacceptable (audit trails written to a local file, for example), and only if the sink is fast enough to drain within your latency budget.

{{< insight >}}
**Serilog's `WriteTo.Async` and OTel's `BatchExportProcessorOptions` are separate batching layers for separate paths.** If you use `WriteTo.Async(a => a.OpenTelemetry(...))`, Serilog's async wrapper handles the buffering — do not also configure OTel's `BatchExportProcessorOptions` inside the sink options. If you use the OTel SDK's `AddOtlpExporter()` directly (not via Serilog), configure batching via `BatchExportProcessorOptions<LogRecord>` on the exporter. The two patterns are not interchangeable.
{{< /insight >}}

## Multi-Sink Configuration

Different destinations warrant different buffer sizes. A console sink drains fast; a remote endpoint has network latency to absorb:

```csharp
public static LoggerConfiguration CreateMultiSinkLogger(IConfiguration config)
{
    return new LoggerConfiguration()
        .MinimumLevel.Information()
        .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
        .Enrich.FromLogContext()
        .Enrich.WithMachineName()
        .Enrich.WithProcessId()
        .Enrich.WithThreadId()

        // Console: fast drain, small buffer, tolerate drops
        .WriteTo.Async(a => a.Console(
            outputTemplate: "[{Timestamp:HH:mm:ss} {Level:u3}] {Message:lj}{NewLine}{Exception}"),
            bufferSize: 1000,
            blockWhenFull: false)

        // Hourly rolling file: larger buffer, retain 1 week of hourly files
        .WriteTo.Async(a => a.File(
            path: config["Logging:FilePath"]!,
            formatter: new JsonFormatter(),
            rollingInterval: RollingInterval.Hour,
            retainedFileCountLimit: 168),
            bufferSize: 25000,
            blockWhenFull: false)

        // OTel export: large buffer; remote network is the bottleneck
        .WriteTo.Async(a => a.OpenTelemetry(options =>
            {
                options.Endpoint = config["OpenTelemetry:Endpoint"];
                options.Protocol  = OtlpProtocol.GrpcProtobuf;
            }),
            bufferSize: 20000,
            blockWhenFull: false);
}
```

## Context Preservation Across Async Operations

Async logging dequeues and writes records on a background thread. The correlation context — trace ID, user ID, operation name — must be captured at enqueue time, not at write time. `BeginScope` and OTel activity propagation handle this correctly through `AsyncLocal<T>`, which follows the logical execution context across `await` boundaries.

```csharp
public class OrderProcessor
{
    private static readonly ActivitySource ActivitySource =
        new ActivitySource("MyApp.Orders");

    private readonly ILogger<OrderProcessor> _logger;

    public OrderProcessor(ILogger<OrderProcessor> logger) => _logger = logger;

    public async Task ProcessOrderAsync(Order order)
    {
        // BeginScope attaches correlation context to all log records
        // within this async operation, including those on resumed threads
        using var scope = _logger.BeginScope(new Dictionary<string, object>
        {
            ["order_id"]    = order.Id,
            ["customer_id"] = order.CustomerId,
        });

        using var activity = ActivitySource.StartActivity("process_order");

        // Use Stopwatch for duration — activity.Duration is only set
        // after the activity stops (when the using block exits)
        var start = Stopwatch.GetTimestamp();

        _logger.LogInformation("Starting order processing");

        try
        {
            await ProcessOrderSteps(order);

            _logger.LogInformation(
                "Order processing completed in {DurationMs}ms",
                Stopwatch.GetElapsedTime(start).TotalMilliseconds);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "Order processing failed after {DurationMs}ms",
                Stopwatch.GetElapsedTime(start).TotalMilliseconds);
            throw;
        }
    }
}
```

`BeginScope` uses `AsyncLocal<T>` internally. Values set in the scope flow into awaited continuations even when they resume on a different thread pool thread, so async-logged records will carry the correct correlation context regardless of which thread actually drains the buffer.

## Graceful Shutdown

Async logging introduces a shutdown risk: records queued at the moment of shutdown may not have been drained when the process exits. Register a `IHostedService` that explicitly flushes before the process terminates:

```csharp
public class GracefulShutdownService : IHostedService
{
    private readonly ILogger<GracefulShutdownService> _logger;
    private readonly IHostApplicationLifetime _lifetime;

    public GracefulShutdownService(
        ILogger<GracefulShutdownService> logger,
        IHostApplicationLifetime lifetime)
    {
        _logger = logger;
        _lifetime = lifetime;
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _lifetime.ApplicationStopping.Register(OnShutdown);
        return Task.CompletedTask;
    }

    private void OnShutdown()
    {
        // Log before flushing — not after. CloseAndFlush disposes the logger.
        _logger.LogInformation("Application shutdown initiated — flushing log queues");

        // Drain all async sinks and deliver buffered records to their destinations
        Log.CloseAndFlush();

        // Do NOT log after CloseAndFlush; the logger is disposed at this point
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
```

Register it in `Program.cs`:

```csharp
services.AddHostedService<GracefulShutdownService>();
```

`Log.CloseAndFlush()` blocks until all queued records have been delivered. The background thread draining the buffer runs to completion before the method returns. On a healthy system this takes milliseconds; on a slow remote sink it may take longer — factor this into your shutdown timeout (`hostBuilder.UseShutdownTimeout(...)`).

## Resilient Fallback

If the async logger's queue fills and `blockWhenFull: false` drops records, or if the primary logger fails, a synchronous fallback preserves the most critical events:

```csharp
public class ResilientLogger
{
    private readonly ILogger _primary;
    private readonly ILogger _fallback;

    public ResilientLogger(ILogger primary, ILogger fallback)
    {
        _primary  = primary;
        _fallback = fallback;
    }

    public void Log(LogLevel level, string message, params object[] args)
    {
        try
        {
            _primary.Log(level, message, args);
        }
        catch (InvalidOperationException)
        {
            // Primary logger is disposed or faulted — fall through to synchronous sink
            _fallback.Log(level, message, args);
        }
    }
}
```

The fallback logger should write to a fast, local destination — a console sink or a local file — not to a slow remote endpoint. Its purpose is to preserve records when the async path is unavailable, not to maintain full throughput.

## Common Pitfalls

**1. Unbounded queue.** `WriteTo.Async()` has a default `bufferSize` of 10,000. If you pass no arguments, you get that default. Be explicit so the configuration is visible in code review:

```csharp
// Don't: implicit defaults are invisible
.WriteTo.Async(a => a.Console())

// Do: make buffer size and overflow policy explicit
.WriteTo.Async(a => a.Console(), bufferSize: 10000, blockWhenFull: false)
```

**2. Logging every item in a high-volume loop.** Async logging queues records; it does not make them free. At high enough call rates, you will still fill the buffer. Adapt the logging rate to the item count:

```csharp
// Don't: log every item — fills the buffer at large list sizes
foreach (var item in items)
{
    _logger.LogDebug("Processing item {ItemId}", item.Id);
    ProcessItem(item);
}

// Do: log periodically with progress context
var logEveryN = Math.Max(1, items.Count / 100); // log ~100 progress updates

for (int i = 0; i < items.Count; i++)
{
    if (i % logEveryN == 0)
        _logger.LogDebug("Processing batch {Current}/{Total} ({Progress}%)",
            i, items.Count, (i * 100) / items.Count);

    ProcessItem(items[i]);
}
```

**3. Context loss in fire-and-forget.** `Task.Run()` creates a new `AsyncLocal` scope that does not inherit scope values from the parent. Log before launching; do not rely on context flowing into detached tasks:

```csharp
// Don't: context does not propagate into Task.Run()
_logger.LogInformation("Starting process");
await Task.Run(() => DoWork()); // scope values lost inside here

// Do: use async/await to preserve context, or log inside the task with explicit context
using var scope = _logger.BeginScope(new { operation_id = Guid.NewGuid() });
_logger.LogInformation("Starting process");
await DoWorkAsync(); // scope propagates through await
```

## Testing Async Logging

Async logging tests must account for the fact that records are written on background threads — assertions made immediately after logging may run before the drain completes:

```csharp
[Test]
public async Task AsyncLogging_UnderLoad_DoesNotBlockCallers()
{
    var logger = new LoggerConfiguration()
        .WriteTo.Async(a => a.Console(), bufferSize: 100, blockWhenFull: false)
        .CreateLogger();

    var stopwatch = Stopwatch.StartNew();

    // Emit 1000 records concurrently
    var tasks = Enumerable.Range(0, 1000)
        .Select(i => Task.Run(() => logger.Information("Test message {MessageId}", i)))
        .ToArray();

    await Task.WhenAll(tasks);
    stopwatch.Stop();

    // Enqueueing 1000 records should complete well under 1 second
    // (the drain may continue in the background)
    Assert.That(stopwatch.ElapsedMilliseconds, Is.LessThan(1000));
}

[Test]
public void AsyncLogging_OnFlush_DeliversAllQueuedMessages()
{
    var sink    = new InMemorySink();
    var logger  = new LoggerConfiguration()
        .WriteTo.Async(a => a.Sink(sink), bufferSize: 1000)
        .CreateLogger();

    for (int i = 0; i < 100; i++)
        logger.Information("Message {MessageId}", i);

    // CloseAndFlush blocks until all queued records are delivered
    Log.CloseAndFlush();

    Assert.That(sink.Events.Count, Is.EqualTo(100));
}
```

`InMemorySink` can be implemented as a simple `ILogEventSink` that appends to a `ConcurrentBag<LogEvent>`, or you can use the `Serilog.Sinks.TestCorrelator` package which provides `TestCorrelator.CreateContext()` and `TestCorrelator.GetLogEventsFromCurrentContext()`.

For extreme-throughput scenarios — `Channel<T>`, `BoundedChannelOptions.DropOldest`, multiple concurrent consumers — see [High-Throughput Logging](/guides/high-throughput-logging/).

- [High-Throughput Logging](/guides/high-throughput-logging/) — `Channel<T>` and multi-consumer patterns for 100k+ req/s
- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — the field choices that make async log records useful downstream
- [Logging Foundations](/guides/logging-foundations/) — log levels, what to log, and context philosophy
