---
title: "Enrich Logs with Business Context in .NET"
date: 2026-06-10
draft: false
excerpt: "Log lines that say 'payment failed' tell you something broke. Log lines that say 'payment failed, enterprise customer, £12,400 basket' tell you what to do about it. Here is how to inject business context automatically into every log event using Serilog enrichers."
readtime: 7
tags: ["Logs", "Structured Logging", "OpenTelemetry", "Best Practices"]
---

> "The difference between a log line and a clue is context."
> — Anonymous

Your service knows things that your logs don't. It knows the customer's tier. It knows whether the failing request belongs to a trial account or an enterprise contract. It knows the request is part of an A/B experiment. It knows the user's preferred language and region.

None of that appears in most log lines. So when something breaks, your logs tell you *that* it broke — but not *who it matters to* or *how much*.

Adding that context manually to every log call is the wrong approach. It is inconsistent, it is forgotten under pressure, and it bloats every call site with concern-crossing noise. The right approach is to add it automatically, at the framework level, so that every log event your service emits carries the business context that makes it useful — without anyone having to remember to include it.

That is what Serilog enrichers are for.

{{< obs-log-enrichment-before-after >}}

## What Enrichers Do

Serilog's enricher pipeline runs before every log event is written to any sink. An enricher is a class that implements `ILogEventEnricher`, receives the `LogEvent` and a `LogEventPropertyFactory`, and can add, modify, or remove properties. The enricher runs once per log call. The properties it adds appear in every log event for the lifetime of the enrichment scope.

The pattern is exactly right for business context: resolve the context once (from the HTTP request, from a service call, from the ambient DI container), attach it to the logger, and let it flow into every log line that follows.

## Building the Enricher

The enricher resolves business context from the current HTTP request. It reads a few key attributes — customer tier, revenue segment, experiment assignment — and attaches them as structured properties.

```csharp
using Microsoft.AspNetCore.Http;
using Serilog.Core;
using Serilog.Events;

public class BusinessContextEnricher : ILogEventEnricher
{
    private readonly IHttpContextAccessor _httpContextAccessor;
    private readonly ICustomerContextService _customerContext;

    public BusinessContextEnricher(
        IHttpContextAccessor httpContextAccessor,
        ICustomerContextService customerContext)
    {
        _httpContextAccessor = httpContextAccessor;
        _customerContext = customerContext;
    }

    public void Enrich(LogEvent logEvent, ILogEventPropertyFactory propertyFactory)
    {
        var httpContext = _httpContextAccessor.HttpContext;
        if (httpContext is null) return;

        // Resolve customer context — cached per request via ICustomerContextService
        var customer = _customerContext.GetCurrentCustomer(httpContext);
        if (customer is null) return;

        logEvent.AddPropertyIfAbsent(
            propertyFactory.CreateProperty("customer.tier", customer.Tier));

        logEvent.AddPropertyIfAbsent(
            propertyFactory.CreateProperty("customer.segment", customer.RevenueSegment));

        logEvent.AddPropertyIfAbsent(
            propertyFactory.CreateProperty("customer.id", customer.AnonymisedId));

        // Feature flag / experiment context
        var experiment = _customerContext.GetExperimentContext(httpContext);
        if (experiment is not null)
        {
            logEvent.AddPropertyIfAbsent(
                propertyFactory.CreateProperty("experiment.id", experiment.Id));
            logEvent.AddPropertyIfAbsent(
                propertyFactory.CreateProperty("experiment.variant", experiment.Variant));
        }
    }
}
```

The enricher uses `AddPropertyIfAbsent` throughout. This means that if a specific log call explicitly sets `customer.tier`, the explicit value wins — the enricher does not overwrite deliberate callsite decisions.

### The Customer Context Service

The enricher delegates resolution to `ICustomerContextService`, which owns the caching logic. Without caching, every log call would trigger a service lookup — a tax you do not want to pay per log line.

```csharp
public interface ICustomerContextService
{
    CustomerContext? GetCurrentCustomer(HttpContext httpContext);
    ExperimentContext? GetExperimentContext(HttpContext httpContext);
}

public class CustomerContextService : ICustomerContextService
{
    private readonly ICustomerRepository _repository;

    // Cache on the HttpContext items dictionary — lives exactly one request
    private const string CacheKey = "business_context_customer";

    public CustomerContext? GetCurrentCustomer(HttpContext httpContext)
    {
        if (httpContext.Items.TryGetValue(CacheKey, out var cached))
            return cached as CustomerContext;

        var userId = httpContext.User.FindFirst("sub")?.Value;
        if (userId is null) return null;

        var customer = _repository.GetByUserId(userId);
        httpContext.Items[CacheKey] = customer;
        return customer;
    }

    public ExperimentContext? GetExperimentContext(HttpContext httpContext)
    {
        // Feature flag assignments typically arrive as claims or headers
        var experimentHeader = httpContext.Request.Headers["X-Experiment-Context"].ToString();
        if (string.IsNullOrEmpty(experimentHeader)) return null;

        return ExperimentContext.ParseFromHeader(experimentHeader);
    }
}

public record CustomerContext(
    string Tier,           // "enterprise", "growth", "starter", "trial"
    string RevenueSegment, // "high", "mid", "low"
    string AnonymisedId    // hashed — never the raw customer ID
);

public record ExperimentContext(string Id, string Variant);
```

The cache key on `HttpContext.Items` is a deliberate choice. It ties the cache lifetime to the request — no risk of stale data leaking between requests, no manual invalidation needed.

## Wiring It Up

Register the enricher and its dependencies in `Program.cs`:

```csharp
builder.Services.AddHttpContextAccessor();
builder.Services.AddScoped<ICustomerContextService, CustomerContextService>();
builder.Services.AddScoped<BusinessContextEnricher>();

builder.Host.UseSerilog((context, services, configuration) =>
{
    configuration
        .MinimumLevel.Information()
        .Enrich.FromLogContext()
        .Enrich.WithMachineName()
        .Enrich.With(services.GetRequiredService<BusinessContextEnricher>())
        .WriteTo.OpenTelemetry(options =>
        {
            options.Endpoint = context.Configuration["Otlp:Endpoint"];
            options.ResourceAttributes = new Dictionary<string, object>
            {
                ["service.name"] = context.Configuration["ServiceName"] ?? "unknown",
                ["service.version"] = context.Configuration["ServiceVersion"] ?? "unknown"
            };
        });
});
```

The enricher is registered as `Scoped` because it depends on `IHttpContextAccessor`, which is request-scoped. Serilog resolves the enricher from the DI container per log call when you use `Enrich.With(services.GetRequiredService<>())` — this works correctly with scoped dependencies inside ASP.NET Core's request pipeline.

## What the Output Looks Like

Before enrichment, a payment failure looks like this:

```json
{
  "timestamp": "2026-06-10T14:32:01Z",
  "level": "Error",
  "message": "Payment processing failed",
  "exception": "PaymentGatewayException: Gateway timeout"
}
```

After enrichment, the same event carries enough context for triage:

```json
{
  "timestamp": "2026-06-10T14:32:01Z",
  "level": "Error",
  "message": "Payment processing failed",
  "exception": "PaymentGatewayException: Gateway timeout",
  "customer.tier": "enterprise",
  "customer.segment": "high",
  "customer.id": "cus_8f2a9c3d",
  "experiment.id": "checkout-v2",
  "experiment.variant": "streamlined"
}
```

The difference is the difference between "the payment service is broken" and "the payment service is broken for enterprise customers on the streamlined checkout experiment." One of those is a 2am page. The other is a 2am page *with a theory*.

## Scoping Enrichment to a Block

Sometimes you want to add business context for a specific operation — not for all logs in the request. Serilog's `LogContext.PushProperty` creates a scoped enrichment that cleans itself up on disposal:

```csharp
public async Task ProcessOrderAsync(Order order)
{
    using var _ = LogContext.PushProperty("order.id", order.Id);
    using var __ = LogContext.PushProperty("order.value", order.TotalAmount);
    using var ___ = LogContext.PushProperty("order.item_count", order.Items.Count);

    _logger.LogInformation("Starting order processing");

    await ValidateInventoryAsync(order);
    await ChargePaymentAsync(order);
    await DispatchFulfillmentAsync(order);

    _logger.LogInformation("Order processing complete");
    // All three logs above carry order.id, order.value, order.item_count
}
// Properties are removed from context here
```

This is composable with the request-level enricher: the per-request context (customer tier, experiment) is always present; the per-operation context (order ID, basket value) is present only within that block.

## What to Put in Business Context

Good candidates for automatic enrichment:

- **Customer tier / plan** — tells you whether a failure affects paying customers and at what level
- **Revenue segment** — high/mid/low grouping rather than raw ARR (avoid logging financial figures)
- **Feature flag or experiment assignment** — essential for diagnosing regressions introduced by experiments
- **Anonymised customer ID** — hashed, not raw, so correlated logs can be queried by customer without raw PII in logs

What to leave out:

- **Raw customer PII** — names, emails, phone numbers do not belong in logs. Use an anonymised or hashed ID for correlation, and retrieve the human-readable form from your CRM at investigation time.
- **Session tokens or auth credentials** — never, under any circumstances.
- **High-cardinality unbounded values** — if a field has millions of distinct values (raw product SKUs, full URL paths), it will blow up your log index cardinality. Categorise or cap these first.

## Verifying the Enrichment Is Working

A quick unit test to confirm the enricher attaches the right properties:

```csharp
[Fact]
public async Task BusinessContextEnricher_AttachesCustomerTier()
{
    // Arrange
    var sink = new ListSink();
    var logger = new LoggerConfiguration()
        .Enrich.With(new BusinessContextEnricher(
            httpContextAccessor: BuildFakeContextAccessor("user_123"),
            customerContext: new StubCustomerContextService(
                tier: "enterprise", segment: "high")))
        .WriteTo.Sink(sink)
        .CreateLogger();

    // Act
    logger.Information("Test event");

    // Assert
    var logged = sink.Events.Single();
    Assert.Equal("enterprise", logged.Properties["customer.tier"].ToString().Trim('"'));
    Assert.Equal("high", logged.Properties["customer.segment"].ToString().Trim('"'));
}
```

For the `ListSink` and full test patterns, see the companion how-to on [testing structured log output](/howtos/test-structured-logging-dotnet/).

Every log event your service emits now carries the business context that makes it actionable — without anyone at a call site having to remember to include it. That is the kind of observability that pays off at 2am.

<!-- TODO: Add section on enrichment for background workers / hosted services (no HttpContext) -->
<!-- TODO: Add example using W3C Baggage for cross-service business context propagation -->
<!-- TODO: Cross-reference to wire-trace-ids-into-logs.md for trace context enrichment -->
