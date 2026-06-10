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
            // Do not record 404s as errors — they are expected
            opts.RecordException = false;
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
    // Include trace context (TraceId, SpanId) in every log record
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

## Background Services and Workers

`BackgroundService` implementations run outside the HTTP pipeline — there is no incoming request to seed `Activity.Current`. Each iteration of the worker loop should create its own root span:

```csharp
public class OrderProcessingWorker : BackgroundService
{
    private static readonly ActivitySource ActivitySource = new("Commerce.OrderWorker");
    private readonly ILogger<OrderProcessingWorker> _logger;
    private readonly IOrderRepository _orders;

    public OrderProcessingWorker(ILogger<OrderProcessingWorker> logger, IOrderRepository orders)
    {
        _logger = logger;
        _orders = orders;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            using var activity = ActivitySource.StartActivity("worker.process_pending_orders");
            try
            {
                var pending = await _orders.GetPendingAsync();
                activity?.SetTag("orders.pending_count", pending.Count);

                foreach (var order in pending)
                {
                    using var orderActivity = ActivitySource.StartActivity("worker.process_single_order");
                    orderActivity?.SetTag("order.id", order.Id);
                    orderActivity?.SetTag("order.tier", order.CustomerTier);
                    await _orders.ProcessAsync(order);
                }

                activity?.SetStatus(ActivityStatusCode.Ok);
            }
            catch (Exception ex)
            {
                activity?.RecordException(ex);
                activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
                _logger.LogError(ex, "Worker cycle failed");
            }

            await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
        }
    }
}
```

Register the worker's `ActivitySource` in the tracing setup alongside your other sources:

```csharp
.WithTracing(tracing => tracing
    // ... existing config ...
    .AddSource("Commerce.OrderWorker"))
```

### Context in fire-and-forget tasks

When you dispatch `Task.Run` inside an existing traced context, `Activity.Current` will be `null` on the thread-pool thread unless you capture it before dispatching:

```csharp
public async Task<IActionResult> CreateOrderAsync(CreateOrderRequest request)
{
    var order = await _orders.CreateAsync(request);

    // Capture BEFORE Task.Run — Activity.Current is null inside the lambda
    var parentContext = Activity.Current?.Context ?? default;

    _ = Task.Run(async () =>
    {
        using var activity = ActivitySource.StartActivity(
            "notifications.send_confirmation",
            ActivityKind.Internal,
            parentContext);

        activity?.SetTag("order.id", order.Id);
        await _notifications.SendConfirmationAsync(order);
    });

    return Ok(order);
}
```

Without `parentContext`, the notification span has no parent and appears as a disconnected root trace — you cannot find it from the originating HTTP request.

## Message Queue Instrumentation

HTTP instrumentation propagates trace context automatically via the `traceparent` header. Message queues do not — you must inject context into message attributes on the producer side and extract it on the consumer side.

**Producer** — inject before publishing:

```csharp
public async Task PublishOrderCreatedAsync(Order order)
{
    using var activity = ActivitySource.StartActivity("orders.publish", ActivityKind.Producer);
    activity?.SetTag("order.id", order.Id);
    activity?.SetTag("messaging.system", "rabbitmq");
    activity?.SetTag("messaging.destination", "order-events");

    var message = new OrderCreatedMessage { OrderId = order.Id };
    message.Headers = new Dictionary<string, string>();

    // Inject current trace context into message headers
    Propagators.DefaultTextMapPropagator.Inject(
        new PropagationContext(Activity.Current?.Context ?? default, Baggage.Current),
        message.Headers,
        (headers, key, value) => headers[key] = value);

    await _bus.PublishAsync("order-events", message);
}
```

**Consumer** — extract before processing:

```csharp
public async Task HandleOrderCreatedAsync(OrderCreatedMessage message)
{
    // Extract the propagated trace context from message headers
    var propagationContext = Propagators.DefaultTextMapPropagator.Extract(
        default,
        message.Headers,
        (headers, key) =>
            headers.TryGetValue(key, out var value)
                ? new[] { value }
                : Array.Empty<string>());

    using var activity = ActivitySource.StartActivity(
        "orders.handle_created",
        ActivityKind.Consumer,
        propagationContext.ActivityContext);

    activity?.SetTag("order.id", message.OrderId);
    activity?.SetTag("messaging.system", "rabbitmq");
    activity?.SetTag("messaging.destination", "order-events");

    await _orders.HandleCreatedAsync(message.OrderId);
}
```

`ActivityKind.Producer` and `ActivityKind.Consumer` follow the OpenTelemetry messaging semantic conventions. Trace backends use these kinds to link publisher and subscriber spans across the queue boundary.

`Propagators.DefaultTextMapPropagator` uses W3C `traceparent` by default — the same format propagated in HTTP headers — so no additional configuration is required on either side. The consumer span appears as a child of the producer span in the same trace.

---

- [OTel Context Propagation](/guides/otel-context-propagation/) — W3C traceparent, B3, and where propagation breaks across async boundaries
- [How to Configure Prometheus for Your Service](/howtos/configure-prometheus/) — adding the metrics pipeline to the setup above

<!-- TODO: Add section on the .NET zero-code instrumentation agent (for legacy services you cannot modify) -->
<!-- TODO: Add section on ASP.NET Core Minimal API vs Controller instrumentation differences -->
<!-- TODO: Add section on connecting trace context to Serilog structured logs (if not using ILogger bridge) -->
