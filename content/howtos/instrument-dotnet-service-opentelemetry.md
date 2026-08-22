---
title: "How to Instrument a .NET Service with OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "Add OpenTelemetry to an ASP.NET Core service — auto-instrumentation for HTTP, Entity Framework, and gRPC, manual spans for business logic, and correlated logs via ILogger — all routed through a local Collector."
readtime: 8
tags: ["OpenTelemetry", "Tracing", "Observability", "How-to"]
---

OpenTelemetry has first-class .NET support. The SDK covers traces, metrics, and logs, and the auto-instrumentation packages cover ASP.NET Core, Entity Framework Core, HttpClient, gRPC, and more with no manual code changes required.

## Dependencies

Add the core packages to your project:

```xml
<PackageReference Include="OpenTelemetry" Version="1.9.0" />
<PackageReference Include="OpenTelemetry.Extensions.Hosting" Version="1.9.0" />
<PackageReference Include="OpenTelemetry.Exporter.OpenTelemetryProtocol" Version="1.9.0" />

<!-- Auto-instrumentation packages -->
<PackageReference Include="OpenTelemetry.Instrumentation.AspNetCore" Version="1.9.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.Http" Version="1.9.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.EntityFrameworkCore" Version="1.0.0-beta.12" />
<PackageReference Include="OpenTelemetry.Instrumentation.GrpcNetClient" Version="1.9.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.Runtime" Version="1.9.0" />
```

## SDK Initialisation

Configure all three signals in `Program.cs`. The important pattern: the `TracerProvider`, `MeterProvider`, and `LoggerProvider` are configured once at startup using the `IServiceCollection` extensions — never instantiated directly with `new`.

```csharp
var builder = WebApplication.CreateBuilder(args);

// Resource attributes — the identity of this service
var resourceBuilder = ResourceBuilder.CreateDefault()
    .AddService(
        serviceName: "checkout-api",
        serviceNamespace: "commerce",
        serviceVersion: "1.4.2")
    .AddAttributes(new Dictionary<string, object>
    {
        ["deployment.environment"] = builder.Environment.EnvironmentName.ToLower()
    });

// Traces
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing => tracing
        .SetResourceBuilder(resourceBuilder)
        .AddAspNetCoreInstrumentation(opts =>
        {
            // RecordException controls whether unhandled exceptions are recorded as
            // exception events on the span — it has no effect on HTTP status codes.
            // Leave it off unless you want exception stack traces attached to spans.
            opts.RecordException = false;
            // Note: 404s are not marked as span errors by default — only 5xx responses
            // are, per HTTP semantic conventions — so no extra config is needed for that.
            opts.Filter = ctx => ctx.Request.Path != "/health";
        })
        .AddHttpClientInstrumentation()
        .AddEntityFrameworkCoreInstrumentation()
        .AddGrpcClientInstrumentation()
        .AddOtlpExporter(opts =>
        {
            opts.Endpoint = new Uri("http://localhost:4317");
        }))

    // Metrics
    .WithMetrics(metrics => metrics
        .SetResourceBuilder(resourceBuilder)
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()        // GC, thread pool, heap
        .AddOtlpExporter(opts =>
        {
            opts.Endpoint = new Uri("http://localhost:4317");
        }));

// Logs — bridge existing ILogger output into OTel
builder.Logging.AddOpenTelemetry(logging =>
{
    logging.SetResourceBuilder(resourceBuilder);
    logging.AddOtlpExporter(opts =>
    {
        opts.Endpoint = new Uri("http://localhost:4317");
    });
    // TraceId and SpanId are injected into every log record automatically from
    // Activity.Current — no toggle required. IncludeTraceState instead controls
    // whether the W3C tracestate string is attached to log records.
    logging.IncludeTraceState = true;
    logging.IncludeScopes = true;
});
```

## Manual Spans for Business Logic

Auto-instrumentation covers framework boundaries. For business logic operations, add spans manually using an `ActivitySource` — the .NET equivalent of the OTel `Tracer`:

```csharp
public class PaymentService
{
    // One ActivitySource per assembly, shared across the class
    private static readonly ActivitySource ActivitySource =
        new ActivitySource("Commerce.PaymentService");

    private readonly ILogger<PaymentService> _logger;

    public PaymentService(ILogger<PaymentService> logger) => _logger = logger;

    public async Task<PaymentResult> ChargeAsync(Order order)
    {
        // Start a span. using ensures it ends when the block exits.
        using var activity = ActivitySource.StartActivity("payment.charge");

        // Add attributes that describe this specific operation
        activity?.SetTag("payment.amount", order.TotalAmount);
        activity?.SetTag("payment.currency", order.Currency);
        activity?.SetTag("payment.provider", "stripe");
        activity?.SetTag("order.id", order.Id);

        try
        {
            var result = await _stripeClient.ChargeAsync(order);

            activity?.SetTag("payment.charge_id", result.ChargeId);
            // Explicit OK is optional — UNSET is fine for success
            activity?.SetStatus(ActivityStatusCode.Ok);

            _logger.LogInformation(
                "Payment charged successfully for order {OrderId}", order.Id);

            return result;
        }
        catch (StripeException ex) when (ex.StripeError?.Type == "card_error")
        {
            // Card declined: a business outcome, not a system error
            activity?.SetTag("payment.decline_code", ex.StripeError.Code);
            activity?.AddEvent(new ActivityEvent("payment.declined",
                tags: new ActivityTagsCollection
                {
                    ["payment.decline_code"] = ex.StripeError.Code
                }));
            // Do NOT set ERROR — this is expected behaviour
            return PaymentResult.Declined(ex.StripeError.Code);
        }
        catch (Exception ex)
        {
            // System failure: set ERROR and record the exception
            activity?.RecordException(ex);
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);

            _logger.LogError(ex,
                "Payment charge failed for order {OrderId}", order.Id);
            throw;
        }
    }
}
```

Register the `ActivitySource` with the tracer so its spans are captured:

```csharp
.WithTracing(tracing => tracing
    // ... existing config ...
    .AddSource("Commerce.PaymentService"))   // matches the name in new ActivitySource(...)
```

## Custom Metrics

For business metrics, use the `Meter` class directly. The .NET OTel metrics API uses the same instrument types as the spec: `Counter`, `Histogram`, `UpDownCounter`, and observable variants.

```csharp
public class OrderMetrics
{
    private static readonly Meter Meter = new Meter("Commerce.Orders");

    // Counter: only goes up, counts occurrences
    private static readonly Counter<long> OrdersCreated =
        Meter.CreateCounter<long>("orders.created",
            unit: "{orders}",
            description: "Total number of orders created");

    // Histogram: records distribution of values (latency, sizes)
    private static readonly Histogram<double> PaymentDuration =
        Meter.CreateHistogram<double>("payment.duration",
            unit: "ms",
            description: "Duration of payment processing");

    // UpDownCounter: can go up and down (queue depth, active connections)
    private static readonly UpDownCounter<long> ActiveCheckouts =
        Meter.CreateUpDownCounter<long>("checkouts.active",
            unit: "{checkouts}",
            description: "Number of checkout sessions currently in progress");

    public void RecordOrderCreated(string currency) =>
        OrdersCreated.Add(1, new TagList { { "currency", currency } });

    public void RecordPaymentDuration(double ms, string provider) =>
        PaymentDuration.Record(ms, new TagList { { "provider", provider } });

    public void CheckoutStarted() => ActiveCheckouts.Add(1);
    public void CheckoutEnded() => ActiveCheckouts.Add(-1);
}
```

Register the Meter the same way as the ActivitySource:

```csharp
.WithMetrics(metrics => metrics
    // ... existing config ...
    .AddMeter("Commerce.Orders"))
```

## Verifying the Setup

Run a local Collector and check signals are arriving:

```yaml
# docker-compose.yml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    volumes:
      - ./collector-config.yaml:/etc/otelcol-contrib/config.yaml
```

```yaml
# collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  debug:
    verbosity: detailed   # logs spans to stdout for local dev

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      exporters: [debug]
    logs:
      receivers: [otlp]
      exporters: [debug]
```

Send a request to your service and check the Collector output for spans with your `service.name`, `deployment.environment`, and custom attributes.

<!-- TODO: Add section on the .NET zero-code instrumentation agent (for legacy services you cannot modify) -->
<!-- TODO: Add section on ASP.NET Core Minimal API vs Controller instrumentation differences -->
<!-- TODO: Add section on background services and Worker instrumentation -->
<!-- TODO: Add section on connecting trace context to Serilog structured logs (if not using ILogger bridge) -->
