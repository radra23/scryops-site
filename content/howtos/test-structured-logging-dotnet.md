---
title: "Test Structured Log Output in .NET"
date: 2026-06-10
draft: true
excerpt: "If your logs are part of your observability contract, they deserve tests. Here is how to write assertions against structured log properties — verifying schema, severity, and that sensitive data is not leaking — using Serilog and xUnit."
readtime: 6
tags: ["Logs", "Structured Logging", "Best Practices"]
---

> "You test the code that runs the system. You should test the code that watches it too."
> — Anonymous

Structured logging is not just formatting. When you make a deliberate choice to emit `payment.provider` alongside `payment.duration_ms`, you are defining a contract — downstream dashboards, alerts, and queries depend on that field existing with that name. If a refactor renames the property, silently and without a failing test, your dashboards go dark.

Most teams test their log *volume* informally — they check that things were logged, perhaps by grepping output in integration tests. Almost no teams test the structured *content*: the specific properties, their types, their presence or absence based on code paths, and whether sensitive fields are being correctly masked.

The same patterns apply to NUnit or MSTest.

{{< mermaid caption="Fig. — An in-memory Serilog sink captures the real pipeline output, so tests assert on the properties, PII absence, and levels that actually get written, not what the code intends to write." >}}
flowchart LR
    subgraph sut["Code Under Test"]
        svc["PaymentService<br/>OrderService<br/>UserLookupService"]
    end
    subgraph pipe["Serilog Pipeline"]
        enr["Enrichers"]
        flt["Level Filter"]
        snk["ListSink<br/>(in-memory)"]
    end
    subgraph chk["Test Assertions"]
        prp["Property values<br/>and types"]
        pii["PII absence"]
        lvl["Log levels"]
    end
    svc --> enr --> flt --> snk
    snk --> prp
    snk --> pii
    snk --> lvl
    style snk fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style chk fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
{{< /mermaid >}}

## The Test Sink

The foundation is an in-memory sink that captures log events rather than writing them anywhere. Serilog exposes `ILogEventSink`, which is all you need:

```csharp
using Serilog.Core;
using Serilog.Events;
using System.Collections.Concurrent;

public class ListSink : ILogEventSink
{
    public ConcurrentBag<LogEvent> Events { get; } = new();

    public void Emit(LogEvent logEvent)
    {
        Events.Add(logEvent);
    }
}
```

Build a logger that writes to this sink, run your code against it, then assert on the captured events. The whole pipeline — enrichers, filters, destructuring policies — runs normally. You are testing what actually gets written, not what you think gets written.

## Basic Property Assertions

Here is the pattern for asserting a specific property exists with a specific value:

```csharp
public static class LogEventExtensions
{
    public static string? GetStringProperty(this LogEvent logEvent, string propertyName)
    {
        if (!logEvent.Properties.TryGetValue(propertyName, out var value))
            return null;

        return value is ScalarValue scalar ? scalar.Value?.ToString() : null;
    }

    public static T? GetProperty<T>(this LogEvent logEvent, string propertyName)
        where T : struct
    {
        if (!logEvent.Properties.TryGetValue(propertyName, out var value))
            return null;

        if (value is ScalarValue scalar && scalar.Value is T typedValue)
            return typedValue;

        return null;
    }

    public static bool HasProperty(this LogEvent logEvent, string propertyName)
        => logEvent.Properties.ContainsKey(propertyName);
}
```

With those helpers, assertions read cleanly:

```csharp
public class PaymentServiceLoggingTests
{
    [Fact]
    public async Task ProcessPayment_Success_LogsProviderAndDuration()
    {
        var sink = new ListSink();
        var logger = new LoggerConfiguration()
            .WriteTo.Sink(sink)
            .CreateLogger();

        var service = new PaymentService(
            logger: new SerilogLoggerFactory(logger).CreateLogger<PaymentService>(),
            gateway: new StubPaymentGateway(succeeds: true, latencyMs: 234));

        await service.ProcessAsync(BuildOrder());

        var paymentEvent = sink.Events
            .Single(e => e.MessageTemplate.Text.Contains("payment") &&
                         e.Level == LogEventLevel.Information);

        Assert.Equal("stripe", paymentEvent.GetStringProperty("payment.provider"));
        Assert.Equal(234, paymentEvent.GetProperty<int>("payment.duration_ms"));
        Assert.Equal("completed", paymentEvent.GetStringProperty("payment.status"));
    }

    [Fact]
    public async Task ProcessPayment_GatewayTimeout_LogsErrorWithOrderId()
    {
        var sink = new ListSink();
        var logger = new LoggerConfiguration()
            .WriteTo.Sink(sink)
            .CreateLogger();

        var service = new PaymentService(
            logger: new SerilogLoggerFactory(logger).CreateLogger<PaymentService>(),
            gateway: new StubPaymentGateway(throws: new GatewayTimeoutException("timeout")));

        await Assert.ThrowsAsync<GatewayTimeoutException>(
            () => service.ProcessAsync(BuildOrder(orderId: "ord-9f2a")));

        var errorEvent = sink.Events.Single(e => e.Level == LogEventLevel.Error);

        Assert.Equal("ord-9f2a", errorEvent.GetStringProperty("order.id"));
        Assert.NotNull(errorEvent.Exception);
        Assert.IsType<GatewayTimeoutException>(errorEvent.Exception);
    }
}
```

## Testing That Sensitive Data Is Not Logged

This is the test most teams skip — and the one with the highest stakes. A PII audit failure, a leaked credential in logs, a customer email appearing in a structured property: these are incidents, not bugs.

The pattern is an explicit exclusion test — assert that specific properties are absent, or that present values are in their masked form:

```csharp
public class PiiSafetyTests
{
    [Fact]
    public async Task ProcessPayment_DoesNotLogRawCardNumber()
    {
        var sink = new ListSink();
        var logger = BuildLoggerWithSink(sink);

        var service = new PaymentService(logger, new StubPaymentGateway());

        await service.ProcessAsync(BuildOrderWithCard(cardNumber: "4111111111111111"));

        // No event should contain the raw card number anywhere
        foreach (var logEvent in sink.Events)
        {
            var rendered = logEvent.RenderMessage();
            Assert.DoesNotContain("4111111111111111", rendered);

            // Also check structured properties — the rendered message only covers
            // the message template; properties are stored separately
            foreach (var prop in logEvent.Properties.Values)
            {
                Assert.DoesNotContain("4111111111111111", prop.ToString());
            }
        }
    }

    [Fact]
    public async Task UserLookup_LogsHashedIdNotEmail()
    {
        var sink = new ListSink();
        var logger = BuildLoggerWithSink(sink);

        var service = new UserLookupService(logger, new StubUserRepository());
        await service.FindByEmailAsync("alice@example.com");

        var lookupEvent = sink.Events
            .Single(e => e.HasProperty("user.id"));

        // user.id should be a hash, not the email
        var userId = lookupEvent.GetStringProperty("user.id");
        Assert.NotNull(userId);
        Assert.DoesNotContain("@", userId);
        Assert.DoesNotContain("alice", userId);
        // SHA-256 hex is 64 chars; a hashed ID should be a fixed-length hex string
        Assert.Matches("^[a-f0-9]{16,64}$", userId);
    }

    [Fact]
    public async Task OrderProcessing_EmailAppearsNowhere()
    {
        var sink = new ListSink();
        var logger = BuildLoggerWithSink(sink);

        var service = new OrderService(logger, new StubOrderRepository());
        await service.ProcessAsync(BuildOrder(customerEmail: "bob@example.com"));

        foreach (var logEvent in sink.Events)
        {
            Assert.DoesNotContain("bob@example.com", logEvent.RenderMessage());
            foreach (var prop in logEvent.Properties.Values)
                Assert.DoesNotContain("bob@example.com", prop.ToString());
        }
    }
}
```

Run these tests in CI. A PII leak caught in a test is an almost-incident. A PII leak caught in a log aggregator is an incident.

## Testing Log Levels

Log level choice is part of your observability contract. An operation that degrades silently at `Debug` instead of `Warning` means on-call never knows it happened. An operation that logs at `Error` when it should log at `Warning` creates alert fatigue.

```csharp
public class LogLevelTests
{
    [Theory]
    [InlineData(RetryOutcome.Succeeded, LogEventLevel.Information)]
    [InlineData(RetryOutcome.FailedAfterRetries, LogEventLevel.Warning)]
    [InlineData(RetryOutcome.CircuitOpen, LogEventLevel.Error)]
    public async Task DownstreamCall_LogsCorrectLevel(
        RetryOutcome outcome, LogEventLevel expectedLevel)
    {
        var sink = new ListSink();
        var logger = BuildLoggerWithSink(sink);

        var service = new DownstreamCallerService(
            logger, new StubHttpClient(simulatedOutcome: outcome));

        await service.CallAsync("https://api.example.com/resource");

        Assert.Contains(sink.Events, e => e.Level == expectedLevel);
    }
}
```

## Testing Structured Properties with Enrichers

If you use enrichers — such as the [business context enricher](/howtos/enrich-logs-with-business-context-dotnet/) — you want to test that they actually add the right properties under the right conditions, not just that they compile:

```csharp
public class BusinessContextEnricherTests
{
    [Fact]
    public void Enrich_AddsCustomerTierFromHttpContext()
    {
        var sink = new ListSink();
        var httpContext = BuildFakeHttpContext(userId: "user_123");

        var logger = new LoggerConfiguration()
            .Enrich.With(new BusinessContextEnricher(
                httpContextAccessor: new FakeHttpContextAccessor(httpContext),
                customerContext: new StubCustomerContextService(tier: "enterprise")))
            .WriteTo.Sink(sink)
            .CreateLogger();

        logger.Information("Test event");

        var logged = sink.Events.Single();
        Assert.Equal("enterprise", logged.GetStringProperty("customer.tier"));
    }

    [Fact]
    public void Enrich_DoesNotAddProperties_WhenNoHttpContext()
    {
        var sink = new ListSink();
        var logger = new LoggerConfiguration()
            .Enrich.With(new BusinessContextEnricher(
                httpContextAccessor: new FakeHttpContextAccessor(httpContext: null),
                customerContext: new StubCustomerContextService(tier: "enterprise")))
            .WriteTo.Sink(sink)
            .CreateLogger();

        logger.Information("Background task event");

        var logged = sink.Events.Single();
        Assert.False(logged.HasProperty("customer.tier"));
    }
}
```

The second test is the one teams forget: enrichers that try to access `HttpContext` from a background worker or hosted service will find it null. A test that verifies graceful null handling stops that from becoming a runtime `NullReferenceException`.

## A Note on Test Doubles

The `StubPaymentGateway`, `StubCustomerContextService`, and friends in these examples are simple hand-rolled stubs. For this kind of test, stubs beat mocking frameworks — they are explicit about exactly the state they represent, they have no magic, and they compile cleanly. The test is about the logging behaviour, not about the stub machinery.

If your existing test infrastructure already uses Moq or NSubstitute everywhere, there is no need to diverge — just make the stub return the values that drive the code path you're testing.

Logs that never get tested are logs that drift. Properties get renamed. Sensitive fields leak in. Error levels get quietly downgraded. These tests are the guardrails that keep your observability contract from silently degrading — which is exactly the kind of failure that is hardest to notice until it matters.

<!-- TODO: Add section on snapshot testing for log output (serialised expected JSON) -->
<!-- TODO: Add section on integration test patterns: verifying logs emitted by a full request pipeline -->
<!-- TODO: Cross-reference to pii-in-telemetry.md for the broader PII handling guide -->
