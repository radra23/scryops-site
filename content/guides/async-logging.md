---
title: "Async Logging: Keeping Your Application Threads Free"
date: 2026-06-11
draft: false
excerpt: "A synchronous log write makes the request thread wait on disk or network I/O. Async logging hands that work to a background thread, and quietly adds a queue that can fill up, drop records and lose them at shutdown. How to size it, watch it and flush it, with Serilog, the OpenTelemetry SDK and Python."
readtime: 11
tags: ["Logs", "Observability", "OpenTelemetry", "Reliability"]
---

Synchronous logging is a hidden tax on request latency. Writing to a rolling file or a remote endpoint means I/O: a disk flush, a network round-trip, serialisation. Every bit of it runs on the thread that called `LogInformation`. At low request rates you'll never notice. At high rates, or on the day the disk gets slow, each log statement becomes a small wait that every request has to sit through.

Async logging splits submitting a record from delivering it. The application thread drops the record into an in-memory queue and returns. A background worker drains the queue and does the I/O.

That sounds free. It isn't. You've added a queue, and every queue forces three decisions on you: how big it is, what happens when it's full, and what happens to whatever is still in it when the process exits. Make those decisions on purpose and async logging is one of the cheapest latency wins you'll find. Leave them to the defaults and you get log loss you can't see.

## What Moves Off the Thread, and What Doesn't

Async logging moves the *sink* work: formatting the output and writing it somewhere. It doesn't move the work of creating the event. In Serilog, parsing the message template, capturing properties and running enrichers all happen on the calling thread, before the event is queued. Python's `QueueHandler` does the same: it merges the message with its arguments on the caller's thread so the record can be pickled or handed off safely.

So async logging fixes slow I/O. It doesn't fix logging too much. A tight loop that logs every item still pays for every event, then fills the queue on top. The fix for that is level discipline and sampling, covered in [Log Levels](/guides/log-levels-and-severity/#sampling-high-frequency-events), not a bigger buffer.

## Serilog: `WriteTo.Async()`

In .NET, Serilog's async wrapper lives in the `Serilog.Sinks.Async` package. Wrap a sink in it and that sink's `Emit` runs on a dedicated background worker:

```csharp
// Serilog 4.4, Serilog.Sinks.Async 2.1, Serilog.Sinks.OpenTelemetry 4.2
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Information()
    .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
    .Enrich.FromLogContext()
    .Enrich.WithThreadId()        // Serilog.Enrichers.Thread
    .Enrich.WithMachineName()     // Serilog.Enrichers.Environment

    // Console: synchronous by nature, so wrap it
    .WriteTo.Async(a => a.Console(new RenderedCompactJsonFormatter()),
        bufferSize: 1_000,
        blockWhenFull: false)

    // Rolling file: a slow disk flush shouldn't stall a request
    .WriteTo.Async(a => a.File(
            formatter: new RenderedCompactJsonFormatter(),
            path: config["Logging:FilePath"]!,
            rollingInterval: RollingInterval.Day,
            retainedFileCountLimit: 7),
        bufferSize: 10_000,
        blockWhenFull: false)

    // OTLP: already batched and asynchronous, so NOT wrapped in Async
    .WriteTo.OpenTelemetry(options =>
    {
        options.Endpoint = config["OpenTelemetry:Endpoint"];
        options.Protocol = OtlpProtocol.Grpc;
        options.BatchingOptions.BatchSizeLimit = 1_000;
        options.BatchingOptions.BufferingTimeLimit = TimeSpan.FromSeconds(2);
        options.BatchingOptions.QueueLimit = 100_000;
    })
    .CreateLogger();
```

Note the OpenTelemetry sink. It's already a batched sink: Serilog queues its events in the background and ships them in batches (by default up to 1,000 events, every 2 seconds, with a queue limit of 100,000). Wrapping it in `WriteTo.Async` as well just stacks a second queue in front of the first. You get two places to lose events and two sets of numbers to tune, for no gain. Tune `BatchingOptions` instead. The values above are the defaults, written out so they show up in code review.

{{< insight >}}
**Only wrap sinks that block.** Console and file sinks write on the calling thread, so `WriteTo.Async` earns its keep there. Network sinks built on Serilog's batching (`IBatchedLogEventSink`, which the OpenTelemetry sink uses) already do their I/O in the background. Check how a sink works before you wrap it.
{{< /insight >}}

### bufferSize and blockWhenFull

These two parameters decide what happens when the worker can't keep up.

**`bufferSize`** caps how many events wait in memory. The default is 10,000, so the queue is always bounded, even if you never set it. A buffer that never fills is fine. A buffer that fills regularly means either it's too small for your bursts or the sink is genuinely too slow, and only one of those is fixed by a bigger number.

**`blockWhenFull: false`** (the default) means that when the buffer is full, the *arriving* event is dropped and the caller moves on. It isn't the oldest event that goes; it's the newest one, the one being written right now. Each drop is reported through Serilog's failure listener (by default `SelfLog`, which is silent unless you enable it). Dropping is usually the right trade: a gap in the logs during a spike does less harm than adding sink latency to every request.

**`blockWhenFull: true`** turns the queue into backpressure. When it fills, the calling thread waits for a free slot, so you're back to synchronous logging at exactly the moment the system is under the most strain. Use it only where losing a record is worse than slowing down, and only if the sink can drain within your latency budget.

## Watch the Queue

A queue that drops silently is a monitoring blind spot sitting inside your monitoring. Serilog.Sinks.Async exposes its state through `IAsyncLogEventSinkMonitor`. Pass one in, and you get an inspector with `Count`, `BufferSize` and `DroppedMessagesCount`. Publish those as metrics:

```csharp
sealed class AsyncQueueMetrics : IAsyncLogEventSinkMonitor
{
    static readonly Meter Meter = new("MyApp.Logging");
    IAsyncLogEventSinkInspector? _inspector;

    public AsyncQueueMetrics(string sinkName)
    {
        var tags = new KeyValuePair<string, object?>("sink", sinkName);
        Meter.CreateObservableGauge("logging.async.queue.depth",
            () => new Measurement<int>(_inspector?.Count ?? 0, tags));
        Meter.CreateObservableCounter("logging.async.dropped",
            () => new Measurement<long>(_inspector?.DroppedMessagesCount ?? 0, tags));
    }

    public void StartMonitoring(IAsyncLogEventSinkInspector inspector) => _inspector = inspector;
    public void StopMonitoring(IAsyncLogEventSinkInspector inspector) => _inspector = null;
}

// .WriteTo.Async(a => a.File(...), monitor: new AsyncQueueMetrics("file"))
```

Add the `MyApp.Logging` meter to your OpenTelemetry metrics pipeline and alert on any increase in `logging.async.dropped`. Queue depth sitting near `bufferSize` is your early warning; a rising drop counter means you're already losing logs. These are metrics on purpose: a log line that says "I'm dropping logs" can be dropped by the very queue it's reporting on.

If you'd rather catch dropped events than just count them, Serilog 4.1 and later can route failures to a second sink. `WriteTo.FallbackChain` attaches itself as the failure listener of the primary sink, and the async wrapper reports every drop to it:

```csharp
.WriteTo.FallbackChain(
    wt => wt.Async(a => a.File(...), bufferSize: 10_000),
    wt => wt.Console())   // receives events the async buffer had to drop
```

Keep the fallback fast and local. If it's as slow as the primary, all you've done is move the backlog.

## The OpenTelemetry SDK Is Already Async

If you log through `ILogger` straight into the OpenTelemetry SDK, there's no wrapper to add. The OTLP exporter sits behind a **batch processor** by default, and that processor is a bounded queue with a background export loop, the same pattern as above. The [Logs SDK spec](https://opentelemetry.io/docs/specs/otel/logs/sdk/) sets its defaults: a queue of 2,048 records, batches of up to 512, a 30-second export timeout. When the queue is full, new records are dropped. The Logs SDK spec is stable, and so is the .NET logs implementation.

In .NET you tune it through the processor options on `AddOtlpExporter`:

```csharp
// OpenTelemetry .NET 1.19
builder.Logging.AddOpenTelemetry(logging =>
{
    logging.SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("checkout-api"));
    logging.AddOtlpExporter((exporter, processor) =>
    {
        exporter.Endpoint = new Uri("http://localhost:4317");

        processor.ExportProcessorType = ExportProcessorType.Batch;   // the default
        processor.BatchExportProcessorOptions.MaxQueueSize = 2048;
        processor.BatchExportProcessorOptions.ScheduledDelayMilliseconds = 1000;
        processor.BatchExportProcessorOptions.MaxExportBatchSize = 512;
        processor.BatchExportProcessorOptions.ExporterTimeoutMilliseconds = 30000;
    });
});
```

One detail is worth knowing. The spec's default delay between exports is 1,000 ms, but .NET's log processor defaults to 5,000 ms. The other three values match the spec. If you want the spec's behaviour, set the delay explicitly as above, or use the standard environment variables (`OTEL_BLRP_SCHEDULE_DELAY`, `OTEL_BLRP_MAX_QUEUE_SIZE`, `OTEL_BLRP_MAX_EXPORT_BATCH_SIZE`, `OTEL_BLRP_EXPORT_TIMEOUT`), which the .NET SDK reads.

Pick one path per destination. Either Serilog owns the queue (Serilog sink to OTLP) or the OTel SDK does (`ILogger` to the OTel provider). Configuring both for the same records just buffers them twice.

## Context Is Captured at the Call Site

The usual worry with async logging is losing correlation: if a background thread writes the record, does it still carry the trace ID and the order ID? It does, because context is captured when the event is *created*, on the calling thread, and travels with the event through the queue. Serilog's `LogContext` and `ILogger.BeginScope` both store their values in `AsyncLocal<T>`, which flows with the logical execution context across `await`, and into `Task.Run` and the thread pool.

```csharp
using (logger.BeginScope(new Dictionary<string, object> { ["order_id"] = order.Id }))
{
    logger.LogInformation("Request thread");                       // order_id present
    await SomethingAsync();
    logger.LogInformation("After await");                          // order_id present
    await Task.Run(() => logger.LogInformation("In Task.Run"));    // order_id present
    await orderQueue.Writer.WriteAsync(order.Id);                  // hand-off to a worker...
}

// ...a consumer loop started at application startup:
await foreach (var id in orderQueue.Reader.ReadAllAsync())
    logger.LogInformation("Handled order {OrderId}", id);          // order_id MISSING
```

The scope is lost where work crosses a queue into a loop that was started before the scope existed. The consumer runs in the execution context it captured at startup, not the producer's. That covers `Channel<T>` consumers, `BackgroundService` loops and message handlers. The fix is to make the context part of the message: put the order ID and the trace context into the work item, and open a new scope (and, for tracing, a linked span) when the worker picks it up. [Log Context Enrichment](/guides/log-context-enrichment/) covers what to carry, and [wiring trace IDs into logs](/howtos/wire-trace-ids-into-logs/) covers the trace side.

Two smaller traps. Pass scope state as a dictionary (or a message template with arguments), not an anonymous object: Serilog's `ILogger` provider turns key/value pairs into properties, but an anonymous object becomes a single `Scope` value you can't query by field. And `ExecutionContext.SuppressFlow()` or `UnsafeQueueUserWorkItem` deliberately break the flow, so scopes don't follow work started that way.

## Flush on Shutdown

Whatever is in the queue when the process exits is gone. For Serilog with the static `Log.Logger`, the pattern from Serilog's own hosting docs is a `try`/`finally` around the host:

```csharp
Log.Logger = new LoggerConfiguration()
    .WriteTo.Async(a => a.Console(), monitor: new AsyncQueueMetrics("console"))
    .CreateLogger();

try
{
    var builder = Host.CreateApplicationBuilder(args);
    builder.Services.AddSerilog();   // routes ILogger<T> through Log.Logger
    using var host = builder.Build();
    host.Run();
}
catch (Exception ex)
{
    Log.Fatal(ex, "Host terminated unexpectedly");
}
finally
{
    Log.CloseAndFlush();             // drains every async buffer, then disposes the sinks
}
```

This runs after the host has stopped, so the shutdown messages from your hosted services are in the queue too. Calling `CloseAndFlush` from an `ApplicationStopping` callback instead disposes the logger while the host is still shutting down, and everything logged after that point is lost. The OpenTelemetry SDK path flushes its batch processor when the host disposes the logger provider, so a clean host shutdown is enough there.

Flushing takes time, and that time comes out of your termination budget. On Kubernetes the pod gets `terminationGracePeriodSeconds` (30 by default) between SIGTERM and SIGKILL. A queue that takes longer than that to drain to a slow remote endpoint gets cut off partway. A full queue on a sink that's struggling is exactly the case where that happens.

## Beyond .NET

Every mature logging stack has the same three knobs. Only the defaults differ, and the defaults are where the surprises are.

**Python** ships the pattern in the standard library: `QueueHandler` on the application side, `QueueListener` running the real handlers on a background thread. The examples in the docs use an unbounded `queue.Queue()`. If you bound it, a full queue raises `queue.Full`, which the handler reports as a `--- Logging error ---` traceback on stderr for *every* dropped record. Override `enqueue` to drop quietly and count:

```python
import atexit
import logging
import logging.handlers
import queue
import sys

log_queue = queue.Queue(maxsize=10_000)  # bounded: the default Queue() is not


class DroppingQueueHandler(logging.handlers.QueueHandler):
    """Count and drop records when the queue is full, instead of erroring."""

    dropped = 0

    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            DroppingQueueHandler.dropped += 1


# The slow, real handler lives on the listener's thread
stream = logging.StreamHandler(sys.stdout)
stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

listener = logging.handlers.QueueListener(
    log_queue, stream, respect_handler_level=True
)
listener.start()
atexit.register(listener.stop)  # stop() drains the queue before returning

root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(DroppingQueueHandler(log_queue))

logging.getLogger("checkout").info("order %s placed", "ord_12345")
```

Export `DroppingQueueHandler.dropped` as a metric, the same way as the Serilog counter.

**Java with Logback** uses `AsyncAppender`, and its defaults are the opposite of Serilog's. The queue holds 256 events. Once only 20% of that capacity is left, it starts *discarding TRACE, DEBUG and INFO* events and keeps WARN and ERROR. When the queue is completely full it *blocks*, because `neverBlock` defaults to `false`. To get "keep every level, drop rather than block", say so:

```xml
<configuration>
  <shutdownHook/>  <!-- stops the context, flushing AsyncAppender, on JVM exit -->

  <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>8192</queueSize>
    <discardingThreshold>0</discardingThreshold>  <!-- 0 = keep all levels -->
    <neverBlock>true</neverBlock>                 <!-- drop when full, never stall -->
    <appender-ref ref="FILE" />
  </appender>

  <root level="INFO">
    <appender-ref ref="ASYNC" />
  </root>
</configuration>
```

Whether dropping INFO under pressure is the right call is a judgement about your logs, not about Logback. Just make it on purpose.

## Testing Async Logging

Async sinks make naive tests flaky: an assertion that runs straight after a log call may run before the worker has written anything. Flush before you assert, and flush the logger you actually built:

```csharp
[Test]
public void Dispose_DeliversEverythingQueued()
{
    var sink = new InMemorySink();   // ILogEventSink that appends to a ConcurrentQueue<LogEvent>
    var logger = new LoggerConfiguration()
        .WriteTo.Async(a => a.Sink(sink), bufferSize: 1_000)
        .CreateLogger();

    for (var i = 0; i < 100; i++)
        logger.Information("Message {MessageId}", i);

    // Dispose *this* logger. Log.CloseAndFlush() only flushes the static Log.Logger.
    logger.Dispose();

    Assert.That(sink.Events.Count, Is.EqualTo(100));
}

[Test]
public void FullBuffer_DropsInsteadOfBlocking()
{
    var stuck = new StuckSink();     // Emit() waits on a ManualResetEventSlim
    var monitor = new CapturingMonitor();
    var logger = new LoggerConfiguration()
        .WriteTo.Async(a => a.Sink(stuck), bufferSize: 10, blockWhenFull: false, monitor: monitor)
        .CreateLogger();

    for (var i = 0; i < 100; i++)
        logger.Information("Message {MessageId}", i);   // returns even though the sink is stuck

    // 1 event held by the stuck worker + 10 in the buffer; the rest were dropped
    Assert.That(monitor.Inspector!.DroppedMessagesCount, Is.GreaterThanOrEqualTo(89));

    stuck.Release.Set();
    logger.Dispose();
}
```

The first comment is the one that bites. `Log.CloseAndFlush()` acts on the static `Log.Logger`, so calling it on a test's local logger leaves the queue untouched, and the test only passes when it wins a race. The second test is the one most suites lack: it proves the overflow policy does what the config says, rather than assuming it.

## The Short Version

- Wrap sinks that block (console, file). Leave already-batched sinks (Serilog's OpenTelemetry sink, the OTel SDK exporter) alone, and tune their own batching.
- Every queue is bounded and drops *new* records when full, unless you've configured it to block. Know which one you have.
- Export queue depth and dropped count as metrics, and alert on drops.
- Context travels with the event. It doesn't travel through your own work queues, so carry it in the message.
- Flush after the host stops, and leave room for it in the termination grace period.

For the next step up, multiple consumers, `Channel<T>` and back-pressure at hundreds of thousands of events per second, see [High-Throughput Logging](/guides/high-throughput-logging/). For what goes *into* the records you're queueing, see [Structured Logging](/guides/structured-logging-machine-readable/) and [Logging Foundations](/guides/logging-foundations/). For the mistakes async logging won't save you from, see [Common Logging Pitfalls](/guides/common-logging-pitfalls/).
