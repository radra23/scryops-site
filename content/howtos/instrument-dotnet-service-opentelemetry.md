---
title: "How to Instrument a .NET Service with OpenTelemetry"
date: 2026-10-01
draft: false
excerpt: "Add OpenTelemetry to an ASP.NET Core service: traces, metrics and logs in one setup block, manual spans and metrics for business logic, Serilog, and the zero-code agent for services you can't change. All verified against a local Collector."
readtime: 8
tags: ["OpenTelemetry", "Tracing", "Observability", "How-to"]
---

.NET has the most complete OpenTelemetry support of any runtime. Traces, metrics and logs are all stable, ASP.NET Core and `HttpClient` emit spans and metrics natively, and one setup block in `Program.cs` sends all three signals to a Collector. This guide sets that up, adds your own spans and metrics on top, and checks what arrives.

Everything below was run against an ASP.NET Core service on .NET 10, with OpenTelemetry .NET 1.19 and Collector 0.161.0.

There are two ways in:

- **The SDK in code** (most of this guide). A few NuGet packages and one block in `Program.cs`. Use it for any service you own.
- **The zero-code agent** ([at the end](#services-you-cant-change-the-zero-code-agent)). Environment variables and a startup hook, with no code or package changes. Use it for services you can't rebuild.

## Packages

```xml
<PackageReference Include="OpenTelemetry.Extensions.Hosting" Version="1.19.1" />
<PackageReference Include="OpenTelemetry.Exporter.OpenTelemetryProtocol" Version="1.19.1" />
<PackageReference Include="OpenTelemetry.Instrumentation.AspNetCore" Version="1.19.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.Http" Version="1.19.0" />
<PackageReference Include="OpenTelemetry.Instrumentation.Runtime" Version="1.19.0" />
```

Add instrumentation for the libraries you use, but check the version suffix: `OpenTelemetry.Instrumentation.EntityFrameworkCore` and `OpenTelemetry.Instrumentation.GrpcNetClient` are still pre-release (`1.19.1-beta.1` at the time of writing), so their span names and attributes can change between versions.

## Setup: One Block, Three Signals

```csharp
using OpenTelemetry;              // UseOtlpExporter lives here — easy to miss
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using OpenTelemetry.Metrics;
using OpenTelemetry.Logs;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenTelemetry()
    .ConfigureResource(resource => resource
        .AddService(serviceName: "checkout-api", serviceNamespace: "commerce", serviceVersion: "1.4.2")
        .AddAttributes([new("deployment.environment.name",
            builder.Environment.EnvironmentName.ToLowerInvariant())]))
    .WithTracing(tracing => tracing
        .AddAspNetCoreInstrumentation(o => o.Filter = ctx => ctx.Request.Path != "/health")
        .AddHttpClientInstrumentation()
        .AddSource("Commerce.*"))           // your own ActivitySources, by wildcard
    .WithMetrics(metrics => metrics
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()        // GC, heap, thread pool
        .AddMeter("Commerce.*"))            // your own Meters
    .WithLogging()                          // bridges ILogger into OpenTelemetry
    .UseOtlpExporter();                     // one exporter for all three signals
```

A few things this does that older examples do by hand:

- **`ConfigureResource` once.** Every signal gets the same `service.name`, `service.version` and `deployment.environment.name`. Calling `SetResourceBuilder` per signal is the older pattern, and an easy way to end up with traces and metrics from what looks like two different services.
- **`UseOtlpExporter` once.** It configures traces, metrics and logs together. It can't be mixed with per-signal `AddOtlpExporter` calls; pick one style.
- **No endpoint in code.** The exporter reads the standard variables, so the same build works locally and in every environment:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317   # the default; set it per environment
OTEL_EXPORTER_OTLP_PROTOCOL=grpc                     # or http/protobuf (port 4318)
```

With this in place, the service exports:

- a `SERVER` span for every request, named after its route (`POST /checkout/{orderId}`);
- a `CLIENT` span for every outgoing `HttpClient` call;
- `http.server.request.duration` and `http.client.request.duration` histograms, plus the `dotnet.gc.*` runtime metrics;
- every `ILogger` record with the trace and span IDs of the request that wrote it.

The `/health` filter keeps probe traffic out of your traces.

One detail of the log records: by default the body is the message *template* (`Payment charged for order {OrderId}`), with `OrderId` as a separate attribute. That's what you want for grouping and querying. Set `IncludeFormattedMessage = true` in `WithLogging` if you also want the rendered sentence.

## Minimal APIs and Controllers Report Routes Differently

Both are instrumented the same way, but they don't name their routes the same way. In testing, the same shape of endpoint produced:

- A minimal API, `app.MapGet("/orders/{id}", …)`, reported the span name `GET /orders/{id}` and the route `/orders/{id}`.
- A controller, `OrdersController` with `[Route("api/[controller]")]` and `[HttpGet("{id}")]`, reported `GET api/Orders/{id}` and the route `api/Orders/{id}`.

Controller routes are reported as the template after token replacement: no leading slash, and `[controller]` expanded with the class's capitalisation. Neither is wrong, but a dashboard or alert that groups by `http.route` treats them as different shapes. If a service mixes both styles, or you migrate from one to the other, check your queries against the new names.

## Your Own Spans

Instrumentation covers the framework boundaries. For business operations, use an `ActivitySource`, .NET's equivalent of an OpenTelemetry tracer. Its name must match an `AddSource` pattern (`Commerce.*` above) or its spans go nowhere:

```csharp
public class PaymentService(ILogger<PaymentService> logger, IPaymentGateway gateway)
{
    private static readonly ActivitySource Source = new("Commerce.Payments");

    public async Task<PaymentResult> ChargeAsync(Order order)
    {
        using var activity = Source.StartActivity("payment.charge");
        activity?.SetTag("order.id", order.Id);
        activity?.SetTag("payment.amount", (double)order.Total);

        try
        {
            var result = await gateway.ChargeAsync(order);
            if (result.Declined)
            {
                // A declined card is a business outcome, not a system error: no Error status
                activity?.SetTag("payment.decline_code", result.DeclineCode);
                return result;
            }
            logger.LogInformation("Payment charged for order {OrderId}", order.Id);
            return result;
        }
        catch (Exception ex)
        {
            activity?.AddException(ex);                              // an "exception" event on the span
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            logger.LogError(ex, "Payment failed for order {OrderId}", order.Id);
            throw;
        }
    }
}
```

`Activity.AddException` is built into .NET 9 and later, so you don't need an extension method for it. In the test, the failing call produced a `payment.charge` span with status `Error` and an `exception` event, as a child of the request span. The matching log record carried the same trace ID plus `exception.type`, `exception.message` and `exception.stacktrace`.

## Your Own Metrics

Business metrics use `System.Diagnostics.Metrics`, with a `Meter` whose name matches an `AddMeter` pattern:

```csharp
public class PaymentMetrics
{
    private static readonly Meter Meter = new("Commerce.Payments");

    private static readonly Histogram<double> Duration = Meter.CreateHistogram<double>(
        "payment.duration", unit: "s", description: "Duration of payment processing");

    private static readonly Counter<long> Charges = Meter.CreateCounter<long>(
        "payment.charges", unit: "{charge}", description: "Payment charge attempts");

    public void Record(TimeSpan elapsed, string provider, string outcome)
    {
        Duration.Record(elapsed.TotalSeconds, new TagList { { "payment.provider", provider } });
        Charges.Add(1, new TagList { { "payment.provider", provider }, { "payment.outcome", outcome } });
    }
}
```

Record durations in **seconds**, the unit the semantic conventions use for every `*.duration` histogram, so yours line up with `http.server.request.duration` on the same dashboard. Keep tag values to a small, known set: `payment.outcome` with three values is fine; an order ID as a tag creates a new time series per order.

## Serilog

If your service logs through Serilog rather than the plain `ILogger` pipeline, `.WithLogging()` won't see those events. Use Serilog's OpenTelemetry sink instead:

```csharp
// Serilog.AspNetCore + Serilog.Sinks.OpenTelemetry; using Serilog; using Serilog.Events;
builder.Services.AddSerilog(lc => lc
    .MinimumLevel.Override("Microsoft.AspNetCore", LogEventLevel.Warning)
    .WriteTo.Console()
    .WriteTo.OpenTelemetry(o =>
    {
        o.Endpoint = builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"] ?? "http://localhost:4317";
        o.ResourceAttributes = new Dictionary<string, object> { ["service.name"] = "checkout-api" };
    }));
```

Serilog captures the current trace and span IDs on every event by itself, so the sink exports them with no enricher. In testing, each log record arrived with the trace ID of its request span, the rendered message as the body, the template in `message_template.text`, and properties such as `OrderId` as attributes.

The level override matters. Without it, ASP.NET Core's own per-request Information logs (`Request starting…`, `Executing endpoint…`) go to your backend too, four extra records per request. Keep the tracing and metrics setup from above; the sink only replaces the logging half.

## Background Work and Message Queues

A `BackgroundService` runs outside any request, so nothing starts a trace for it. Start a span per unit of work, such as one batch or one message, rather than one for the whole loop:

```csharp
protected override async Task ExecuteAsync(CancellationToken stoppingToken)
{
    while (!stoppingToken.IsCancellationRequested)
    {
        var pending = await _orders.GetPendingAsync(stoppingToken);
        if (pending.Count > 0)
        {
            using var activity = Source.StartActivity("orders.process_pending");   // a new root trace
            activity?.SetTag("orders.pending_count", pending.Count);
            await _orders.ProcessAsync(pending, stoppingToken);
        }
        await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
    }
}
```

Starting the span only when there's work keeps idle polls from filling your backend with empty traces: one every 30 seconds is 2,880 a day per replica.

Work that a request hands to a background worker through a `Channel<T>` or a message broker loses the request's trace context on the way, unless you carry it. [Context Propagation](/guides/otel-context-propagation/) shows the inject-and-extract pattern for both, tested in .NET and four other runtimes. Check your broker client before writing it by hand: RabbitMQ.Client 7, for example, creates producer and consumer spans itself.

## Services You Can't Change: The Zero-Code Agent

For a service you can't rebuild, [OpenTelemetry .NET Automatic Instrumentation](https://github.com/open-telemetry/opentelemetry-dotnet-instrumentation) attaches at startup through a CLR profiler and startup hook. On Linux:

```bash
curl -sSfL https://github.com/open-telemetry/opentelemetry-dotnet-instrumentation/releases/download/v1.17.0/otel-dotnet-auto-install.sh -O
sh ./otel-dotnet-auto-install.sh          # verifies the release with the GitHub CLI (see below)
. $HOME/.otel-dotnet-auto/instrument.sh   # sets the CORECLR_* and DOTNET_* variables

export OTEL_SERVICE_NAME=checkout-api
export OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=production
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
dotnet checkout.dll
```

The current install script (v1.17.0 when this was tested) verifies the release's signed attestation before installing, and it needs the [GitHub CLI](https://cli.github.com/) (`gh`), with a token, to do it. Install `gh` in your build image and give it a `GH_TOKEN`. The script offers `SKIP_RELEASE_VERIFICATION=true` as an escape hatch, but that skips exactly the supply-chain check you want for something that injects itself into every process.

Pointed at a plain ASP.NET Core app with no OpenTelemetry packages or code, the agent produced the same `SERVER` and `CLIENT` spans, HTTP and runtime metrics, and trace-correlated `ILogger` records as the SDK setup above. What it can't do is know about your business operations. For those, the app needs its own `ActivitySource` and `Meter` code, and you're back to the SDK.

## Verify Against a Local Collector

Run a Collector that prints what it receives:

```yaml
# docker-compose.yml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.161.0   # pin it; :latest changes under you
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    volumes:
      - ./collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro
```

```yaml
# collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:  { receivers: [otlp], exporters: [debug] }
    metrics: { receivers: [otlp], exporters: [debug] }
    logs:    { receivers: [otlp], exporters: [debug] }
```

Then send a few requests, including one that fails, and check the Collector's output for:

- **Resource:** `service.name`, `service.version` and `deployment.environment.name` on spans, metrics *and* logs, not just one of them
- **Spans:** a `SERVER` span per request with an `http.route`, `CLIENT` spans as its children, your `payment.charge` span under it, and `Error` status only where something actually failed
- **Metrics:** `http.server.request.duration` and your own metrics, after the first export interval (60 seconds by default; set `OTEL_METRIC_EXPORT_INTERVAL=5000` locally)
- **Logs:** the same trace ID as the request's spans

From here:

- [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/): what the trace IDs look like in each kind of log output, and how to fix them when they're missing
- [Enrich Logs with Business Context in .NET](/howtos/enrich-logs-with-business-context-dotnet/): who-was-affected fields on every log line
- [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/): before any of this leaves the process
- [Context Propagation](/guides/otel-context-propagation/): keeping traces connected across queues, threads and services
