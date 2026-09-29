---
title: "Enrich Logs with Business Context in .NET"
date: 2026-09-29
draft: false
excerpt: "A log line that says 'payment failed' tells you something broke. One that says 'payment failed, enterprise customer, checkout-v2 experiment' tells you what to do about it. Here's how to add that context to every log event in a .NET service, safely, with Serilog."
readtime: 9
tags: ["Logs", "Structured Logging", "OpenTelemetry", "Best Practices", "How-to"]
---

Your service knows things your logs don't. It knows the customer's tier. It knows whether the failing request belongs to a trial account or an enterprise contract. It knows the request is part of an A/B experiment.

None of that shows up in most log lines. So when something breaks, your logs tell you *that* it broke, but not *who it matters to*.

Adding that context by hand to every log call is the wrong fix. It's inconsistent, it gets forgotten under pressure, and it clutters every call site. The right fix is to look the context up once per request and let it flow into every log event automatically, so nobody has to remember it.

{{< obs-log-enrichment-before-after >}}

## Before You Start

You need:

- An ASP.NET Core service on .NET 8 or later
- `Serilog.AspNetCore`, plus `Serilog.Sinks.OpenTelemetry` to export over OTLP
- A random 32-byte key, base64-encoded, stored wherever you keep secrets

Every sample below was compiled and run against `Serilog.AspNetCore` 10.0.0 and `Serilog.Sinks.OpenTelemetry` 4.2.0 on `net8.0`, and the test in step 5 passes.

## Step 1: Decide What the Context Is

Start with the shape of the context and where it comes from:

```csharp
using System.Security.Cryptography;
using System.Text;

public record CustomerContext(
    string Tier,            // "enterprise", "growth", "starter", "trial"
    string RevenueSegment); // "high", "mid", "low": a band, never an amount

public interface ICustomerContextService
{
    Task<CustomerContext?> GetAsync(string userId, CancellationToken cancellationToken);
}

public sealed class Pseudonymizer(byte[] key)
{
    // Keyed HMAC: stable for correlation, useless without the key.
    public string For(string value) =>
        Convert.ToHexString(HMACSHA256.HashData(key, Encoding.UTF8.GetBytes(value)))[..16].ToLowerInvariant();
}
```

`ICustomerContextService` is yours to implement. Look the customer up in whatever already holds their tier and segment: a database, a cache, a claims transform.

The `Pseudonymizer` is there because you'll want to follow one customer across log lines without logging who they are. A plain hash won't do for that: anyone can hash a list of known IDs and match them. A keyed HMAC gives you the same stable value every time, and it's useless to anyone without the key. It's the same approach [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/) takes. If you've set up its HMAC redactor, use that here instead, so both produce the same pseudonyms.

## Step 2: Resolve It Once per Request

A piece of middleware looks the context up once and pushes it into Serilog's `LogContext`, which every log event in the request picks up:

```csharp
using Serilog.Context;
using Serilog.Core;
using Serilog.Core.Enrichers;

public sealed class BusinessContextMiddleware(RequestDelegate next, Pseudonymizer pseudonymizer)
{
    // Only these experiments and variants ever reach your logs.
    private static readonly Dictionary<string, string[]> KnownExperiments = new()
    {
        ["checkout-v2"] = ["control", "streamlined"],
    };

    public async Task InvokeAsync(HttpContext context, ICustomerContextService customers)
    {
        var properties = new List<ILogEventEnricher>();

        var userId = context.User.FindFirst("sub")?.Value;
        if (userId is not null &&
            await customers.GetAsync(userId, context.RequestAborted) is { } customer)
        {
            properties.Add(new PropertyEnricher("customer.tier", customer.Tier));
            properties.Add(new PropertyEnricher("customer.segment", customer.RevenueSegment));
            properties.Add(new PropertyEnricher("customer.ref", pseudonymizer.For(userId)));
        }

        // Header format: "<experiment>:<variant>", e.g. "checkout-v2:streamlined"
        var header = context.Request.Headers["X-Experiment-Context"].ToString().Split(':');
        if (header is [var id, var variant] &&
            KnownExperiments.TryGetValue(id, out var variants) && variants.Contains(variant))
        {
            properties.Add(new PropertyEnricher("experiment.id", id));
            properties.Add(new PropertyEnricher("experiment.variant", variant));
        }

        using (LogContext.Push(properties.ToArray()))
        {
            await next(context);
        }
    }
}
```

Doing the lookup here, once, instead of inside a Serilog enricher saves you three headaches. An enricher runs on *every* log call, so it would repeat the lookup every time. If the lookup itself logs (EF Core does), an enricher calls back into itself. And an enricher registered at startup can't safely use request-scoped services. The middleware sidesteps all three. It runs once, before anything in the request logs, and gets `ICustomerContextService` from the request's own scope.

The experiment header comes from the client, so treat it as untrusted. Only values you've listed make it into your logs. Anything else, including someone's idea of a clever payload, is ignored.

## Step 3: Wire It Up

Register everything in `Program.cs`, and add the middleware *after* authentication so `context.User` is filled in:

```csharp
using Serilog;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddSerilog(logging => logging
    .MinimumLevel.Information()
    .Enrich.FromLogContext()
    .WriteTo.OpenTelemetry(options =>
    {
        options.Endpoint = builder.Configuration["Otlp:Endpoint"] ?? "http://localhost:4317";
        options.ResourceAttributes = new Dictionary<string, object>
        {
            ["service.name"] = builder.Configuration["ServiceName"] ?? "checkout",
            ["service.version"] = builder.Configuration["ServiceVersion"] ?? "unknown",
        };
    }));

builder.Services.AddSingleton(new Pseudonymizer(
    Convert.FromBase64String(builder.Configuration["Logging:PseudonymKey"]
        ?? throw new InvalidOperationException("Logging:PseudonymKey is not configured"))));
builder.Services.AddScoped<ICustomerContextService, CustomerContextService>();

var app = builder.Build();

app.UseAuthentication();
app.UseMiddleware<BusinessContextMiddleware>();
app.UseAuthorization();
```

`Enrich.FromLogContext()` is the line that makes the middleware's properties appear on log events. Leave it out and nothing happens, silently. A missing key stops the service at startup, which beats logging unhashed IDs because a secret didn't load.

## Step 4: Add Context for One Operation

Some context only matters inside one operation. `LogContext.PushProperty` adds it for a block and takes it away again when the block ends:

```csharp
public async Task ProcessOrderAsync(Order order)
{
    using (LogContext.PushProperty("order.item_count", order.Items.Count))
    using (LogContext.PushProperty("order.value_band", ValueBand(order.Total)))
    {
        _logger.LogInformation("Starting order processing");
        await ValidateInventoryAsync(order);
        await ChargePaymentAsync(order);
        _logger.LogInformation("Order processing complete");
    }
}

private static string ValueBand(decimal total) => total switch
{
    < 50m => "0-50",
    < 200m => "50-200",
    _ => "200+",
};
```

This stacks with the request-level context. Customer tier and experiment are on every line in the request. The order's item count and value band are only there inside the block. The band is deliberate: a range tells you what kind of order failed without putting financial figures in your logs.

## Step 5: Test It

This test runs the middleware against a fake request and checks what reaches the log. It also checks that an unknown experiment value is dropped:

```csharp
using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using Serilog;
using Serilog.Core;
using Serilog.Events;

public class BusinessContextMiddlewareTests
{
    [Fact]
    public async Task Every_log_event_in_the_request_carries_business_context()
    {
        var sink = new ListSink();
        using var logger = new LoggerConfiguration()
            .Enrich.FromLogContext()
            .WriteTo.Sink(sink)
            .CreateLogger();

        var middleware = new BusinessContextMiddleware(
            next: _ => { logger.Error("Payment processing failed"); return Task.CompletedTask; },
            pseudonymizer: new Pseudonymizer(new byte[32]));

        var context = new DefaultHttpContext
        {
            User = new ClaimsPrincipal(new ClaimsIdentity([new Claim("sub", "user_123")], "test"))
        };
        context.Request.Headers["X-Experiment-Context"] = "checkout-v2:<script>";

        await middleware.InvokeAsync(context, new StubCustomers(new("enterprise", "high")));

        var properties = sink.Events.Single().Properties;
        Assert.Equal("\"enterprise\"", properties["customer.tier"].ToString());
        Assert.DoesNotContain("user_123", properties["customer.ref"].ToString());
        Assert.False(properties.ContainsKey("experiment.variant")); // unknown variant: dropped
    }

    private sealed class ListSink : ILogEventSink
    {
        public List<LogEvent> Events { get; } = [];
        public void Emit(LogEvent logEvent) => Events.Add(logEvent);
    }

    private sealed class StubCustomers(CustomerContext customer) : ICustomerContextService
    {
        public Task<CustomerContext?> GetAsync(string userId, CancellationToken cancellationToken) =>
            Task.FromResult<CustomerContext?>(customer);
    }
}
```

Try breaking it: remove the `KnownExperiments` check from the middleware and this test fails, which is how you know it's testing something.

## What the Output Looks Like

To see events locally, add `.WriteTo.Console(new RenderedCompactJsonFormatter())` (from `Serilog.Formatting.Compact`) next to the OpenTelemetry sink. Here's the payment failure from the service above, during a request from an enterprise customer on the `streamlined` checkout variant, trimmed to the interesting fields:

```json
{
  "@l": "Error",
  "@m": "Payment processing failed",
  "customer.tier": "enterprise",
  "customer.segment": "high",
  "customer.ref": "36bb095813943f38",
  "experiment.id": "checkout-v2",
  "experiment.variant": "streamlined",
  "order.item_count": 3,
  "order.value_band": "50-200"
}
```

That's the difference between "the payment service is broken" and "the payment service is broken for enterprise customers on the streamlined checkout". One of those is a 2am page. The other is a 2am page *with a theory*.

## What to Put in Business Context

Good candidates:

- **Customer tier or plan**, so you can see whether a failure hits paying customers
- **Revenue segment**, as a band (high, mid, low), never an amount
- **Experiment or feature-flag assignment**, checked against a list you control
- **A pseudonymous customer reference**, keyed, so you can follow one customer without logging who they are

What to leave out:

- **Personal data.** Names, email addresses and phone numbers don't belong in logs. Correlate on the pseudonym and look the person up in your CRM when you need to.
- **Session tokens and credentials.** Never.
- **Unbounded values.** A field with millions of distinct values, like raw product SKUs or full URL paths, blows up your log index. Group or cap it first.

## Common Pitfalls

**This context skips .NET's logging redaction.** Properties you push into Serilog's `LogContext` never pass through the redaction set up with `EnableRedaction()` in the PII how-to. Whatever you push has to be safe already. That's why the customer reference is hashed in the middleware and the order total goes in as a band.

**Background work has no request.** Hosted services and queue consumers never run your middleware, so their logs won't carry this context. Push the same properties with `LogContext.Push` at the start of each message or job, from whatever that work knows about the customer.

**A missing `Enrich.FromLogContext()` fails silently.** Everything compiles and runs. The properties just never show up. If your enriched fields go missing, check that line first.

## See Also

- [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/) — classifying and redacting personal data before it reaches your logs
- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — the Collector-side controls for everything the application misses
