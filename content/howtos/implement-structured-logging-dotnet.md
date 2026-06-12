---
title: "Implement Structured Logging in .NET"
date: 2026-06-11
draft: true
excerpt: "Concrete patterns for structured logging in ASP.NET Core — ILogger<T> with named templates, BeginScope context strategy, performance middleware, and wiring logs into the OTel pipeline."
readtime: 6
tags: ["Logs", "Structured Logging", "OpenTelemetry", "Observability", "Best Practices"]
---

Structured logging in .NET has two distinct layers: the logging API you call in application code (`Microsoft.Extensions.Logging`) and the sink that captures and exports those records. This how-to covers both, plus the common patterns that make structured output actually queryable.

For the conceptual case for structured logging and the JSON schema conventions, see [Logging Foundations](/guides/logging-foundations/) and [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/).

## Choosing a Sink

`ILogger<T>` is the API you write against. The sink is what captures output and determines the wire format.

### Serilog with JSON output

```csharp
public static class Program
{
    public static void Main()
    {
        Log.Logger = new LoggerConfiguration()
            .WriteTo.Console(new JsonFormatter())
            .WriteTo.OpenTelemetry()   // Serilog.Sinks.OpenTelemetry package
            .CreateLogger();

        // Register with Microsoft.Extensions.Logging
        builder.Services.AddLogging(b => b.AddSerilog());
    }
}
```

`.WriteTo.Console(new JsonFormatter())` emits one JSON object per line — the format expected by Loki, Datadog, and most log aggregators. `.WriteTo.OpenTelemetry()` routes structured records into the OTel pipeline alongside traces and metrics.

### MEL with the OTel bridge

If you're not using Serilog, `Microsoft.Extensions.Logging` feeds into OTel directly via `AddOpenTelemetry`:

```csharp
services.AddLogging(builder =>
{
    builder.AddOpenTelemetry(options =>
    {
        options.SetResourceBuilder(ResourceBuilder.CreateDefault()
            .AddService(configuration.GetValue<string>("ServiceName"))
            .AddEnvironmentVariable()
            .AddAttributes(new Dictionary<string, object>
            {
                // Use string literal — opentelemetry.sdk.resources does not export SERVICE_VERSION
                ["service.version"] = Assembly.GetExecutingAssembly()
                    .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?
                    .InformationalVersion ?? "unknown",
                ["deployment.environment"] = configuration.GetValue<string>("Environment")
            }));

        options.AddConsoleExporter();
        options.AddOtlpExporter();
    });
});
```

When you use the OTel ILogger bridge, `trace_id` and `span_id` are injected into log records automatically from `Activity.Current` — no manual enrichment needed.

## Named Template Syntax

`ILogger<T>` uses named message templates, not format strings. The name inside `{...}` becomes a structured property:

```csharp
public class OrderService
{
    private readonly ILogger<OrderService> _logger;

    public OrderService(ILogger<OrderService> logger) => _logger = logger;

    public async Task ProcessOrder(Order order)
    {
        // ✅ Correct — named placeholders become queryable properties
        _logger.LogInformation("Processing order {OrderId} for customer {CustomerId}",
            order.Id, order.CustomerId);

        // ❌ Wrong — anonymous object is silently ignored; message has no placeholder
        // _logger.LogInformation("Processing order", new { order_id = order.Id });
    }
}
```

Anonymous objects passed as positional arguments when the message has no `{Placeholder}` for them are **silently discarded** by MEL. This is the most common source of missing fields in structured output.

## BeginScope: Adding Context to a Block of Work

`BeginScope` attaches a dictionary of properties to all logs emitted within the scope:

```csharp
public async Task<PaymentResult> ProcessPayment(PaymentRequest request)
{
    using var scope = _logger.BeginScope(new Dictionary<string, object>
    {
        ["operation"]    = "process_payment",
        ["payment_id"]   = request.PaymentId,
        ["customer_id"]  = request.CustomerId,
        ["amount"]       = request.Amount,
        ["currency"]     = request.Currency
    });

    var stopwatch = Stopwatch.StartNew();

    try
    {
        var result = await ProcessPaymentInternal(request);

        _logger.LogInformation(
            "Payment {PaymentId} processed in {DurationMs}ms (gateway: {GatewayCode}, fraud score: {FraudScore})",
            request.PaymentId, stopwatch.ElapsedMilliseconds, result.GatewayCode, result.FraudScore);

        return result;
    }
    catch (PaymentException ex)
    {
        _logger.LogError(ex,
            "Payment {PaymentId} failed after {DurationMs}ms: {FailureReason} (gateway: {GatewayErrorCode})",
            request.PaymentId, stopwatch.ElapsedMilliseconds, ex.Reason, ex.GatewayErrorCode);
        throw;
    }
}
```

The scope fields (`operation`, `payment_id`, `customer_id`, `amount`, `currency`) appear on every log record emitted inside the `using` block — the entry log, the success log, and the error log — without repeating them on each call. The per-event fields (`DurationMs`, `GatewayCode`) go in the template.

Use `BeginScope` for context that spans multiple log calls. Use template parameters for context specific to one event.

## HTTP Request Performance Middleware

A middleware that logs every request's outcome and duration gives you a complete latency and error distribution without instrumenting individual controllers:

```csharp
public class PerformanceLoggingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<PerformanceLoggingMiddleware> _logger;

    public PerformanceLoggingMiddleware(RequestDelegate next,
        ILogger<PerformanceLoggingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var stopwatch = Stopwatch.StartNew();
        var method    = context.Request.Method;
        var path      = context.Request.Path.Value;

        try
        {
            await _next(context);

            _logger.LogInformation(
                "HTTP {Method} {Path} {StatusCode} in {DurationMs}ms",
                method, path, context.Response.StatusCode, stopwatch.ElapsedMilliseconds);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "HTTP {Method} {Path} failed after {DurationMs}ms (status: {StatusCode})",
                method, path, stopwatch.ElapsedMilliseconds, context.Response.StatusCode);
            throw;
        }
    }
}
```

Register it before routing: `app.UseMiddleware<PerformanceLoggingMiddleware>()`.

Do not log `RemoteIpAddress` or `UserAgent` here — both are personal data under GDPR. If you need per-IP analysis, do it through aggregated metrics. See [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) for the full decision tree.

## Async Output

Synchronous log output adds latency to every request. Wrap sinks with Serilog's async wrapper to decouple log emission from the request path:

```csharp
services.AddLogging(builder =>
{
    builder.AddSerilog(new LoggerConfiguration()
        .WriteTo.Async(a => a.Console(new JsonFormatter()))
        .WriteTo.Async(a => a.OpenTelemetry())
        .CreateLogger());
});
```

The async wrapper uses an in-process queue. The default queue size is 10,000 events; if the downstream sink blocks, events beyond that are dropped. Set `blockWhenFull: true` if you cannot tolerate dropped logs, at the cost of request latency under backpressure.

For higher-throughput scenarios, route logs through the OTel Collector instead of writing directly to the backend — the Collector's `batch` processor handles the buffering outside the application process. See [High-Throughput Logging](/guides/high-throughput-logging/).

## Common Pitfalls

**String coercion.** Passing `amount.ToString()` loses the numeric type — the field lands as a string in the backend and breaks range queries. Pass the value directly: `_logger.LogInformation("Amount: {Amount}", amount)` keeps it numeric.

**Flat template sprawl.** Cramming ten fields into one template makes call sites hard to read and produces wide, hard-to-filter log records. Use `BeginScope` for the stable context and keep templates to the 2–4 fields that vary per event.

**Inconsistent field names.** `orderId` vs `order_id` vs `OrderId` across services forces post-hoc normalization at query time. Pick a casing convention (`snake_case` is conventional in OTel semantic conventions) and enforce it via code review or a custom analyzer.

**DEBUG in production.** Debug-level logs in production under non-trivial traffic can multiply storage costs by 10×. Set the minimum log level to `Information` in production and configure `appsettings.Production.json` explicitly rather than relying on a default you might have forgotten.

<!-- TODO: Add section on connecting trace context to Serilog structured logs when NOT using the ILogger bridge (fills TODO in instrument-dotnet-service-opentelemetry.md) -->
<!-- TODO: Add BeginScope pattern for background services and IHostedService -->
<!-- TODO: Cover log level filtering per-namespace (useful for reducing 3rd-party library noise) -->

- [Test Structured Log Output in .NET](/howtos/test-structured-logging-dotnet/) — writing assertions against structured log properties
- [Wire Trace IDs into Logs](/howtos/wire-trace-ids-into-logs/) — connecting logs to the distributed trace they belong to
- [High-Throughput Logging](/guides/high-throughput-logging/) — handling log volume at scale without losing signal
- [Instrument a .NET Service with OpenTelemetry](/howtos/instrument-dotnet-service-opentelemetry/) — the full OTel setup for traces, metrics, and logs
