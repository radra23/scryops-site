---
title: "Log Schema Versioning: Keeping Your Event Structure Honest Over Time"
date: 2026-06-10
draft: false
excerpt: "Log schemas drift. A field gets renamed, a type changes from string to integer, a required property goes missing for three weeks before anyone notices. Schema versioning gives your log pipeline a contract it can enforce — and migrate."
readtime: 8
tags: ["Logs", "Structured Logging", "Observability", "Best Practices"]
---

> "An unversioned schema is a promise you've already broken."
> — Anonymous

Structured logging solves the parsing problem. JSON events with consistent field names beat unstructured text for everything that reads logs programmatically — dashboards, alerts, anomaly detection, incident correlation. The whole argument for structured logging rests on the word *consistent*.

Here is the problem: nothing enforces that consistency over time.

A service runs for two years. Developers come and go. The `user_id` field quietly becomes `userId` in one service, `customerId` in another. The `duration` field that was always milliseconds gets logged as seconds by a new developer who read the field name without seeing the convention. A required field disappears for three sprints because the query that populated it started throwing and someone wrapped it in a try-catch with an empty catch block.

Your dashboards stop working. Your alerts fire on null. Your ML model starts getting garbage features. And you have no way to know when the schema diverged, or by how much, or what it used to look like.

Log schema versioning is the structural answer to this. It gives your events a contract they carry with them — and gives your pipeline a signal when that contract breaks.

## What Schema Versioning Adds to an Event

A versioned log event carries a metadata block alongside its payload. The metadata answers three questions: what schema produced this event, what version of that schema, and is this version compatible with earlier ones?

```csharp
public record SchemaInfo
{
    public string Namespace { get; init; } = "com.myorg.events";
    public string Version { get; init; } = "1.0.0";
    public CompatibilityLevel Compatibility { get; init; } =
        CompatibilityLevel.BackwardCompatible;
    public DateTimeOffset EffectiveFrom { get; init; } = DateTimeOffset.UtcNow;
}

public enum CompatibilityLevel
{
    /// <summary>New readers can read old events. Safe to upgrade readers first.</summary>
    BackwardCompatible,

    /// <summary>Old readers can read new events. Safe to upgrade writers first.</summary>
    ForwardCompatible,

    /// <summary>Both directions are safe. Producers and consumers can upgrade independently.</summary>
    FullCompatible,

    /// <summary>Incompatible change. Readers and writers must be coordinated.</summary>
    Breaking
}
```

The `CompatibilityLevel` mirrors the vocabulary that Confluent Schema Registry and Apache Avro use for message schemas. The same concepts apply to logs: a field rename is a breaking change; adding an optional field is backward compatible; removing a field is forward compatible for readers that don't depend on it, breaking for those that do.

## A Versioned Event Base Type

Rather than sprinkling schema info across ad-hoc log calls, attach it to a base type that all structured events inherit:

```csharp
public abstract record VersionedLogEvent
{
    public SchemaInfo Schema { get; init; } = new();
    public string EventId { get; init; } = Guid.NewGuid().ToString("N")[..16];
    public DateTimeOffset OccurredAt { get; init; } = DateTimeOffset.UtcNow;
    public string EventType { get; init; } = string.Empty;
}

public record PaymentProcessedEvent : VersionedLogEvent
{
    public PaymentProcessedEvent()
    {
        Schema = new SchemaInfo
        {
            Namespace = "com.myorg.payments",
            Version = "2.1.0",
            Compatibility = CompatibilityLevel.BackwardCompatible
        };
        EventType = "payment.processed";
    }

    public string OrderId { get; init; } = string.Empty;
    public string Provider { get; init; } = string.Empty;
    public decimal Amount { get; init; }
    public string Currency { get; init; } = string.Empty;
    public int DurationMs { get; init; }
    public string Status { get; init; } = string.Empty;
}
```

The `EventId` field is worth noting. Log events are typically identified only by their position in a stream or their timestamp. A stable `EventId` lets you deduplicate across retries, correlate a specific event across multiple aggregation pipelines, and ask "did this specific payment-processed event reach the billing service?" — a question that timestamp-based correlation cannot reliably answer.

## Emitting Versioned Events

A typed logger helper enforces the schema at the call site:

```csharp
public class TypedEventLogger<T> where T : VersionedLogEvent
{
    private readonly ILogger<T> _logger;

    public TypedEventLogger(ILogger<T> logger)
    {
        _logger = logger;
    }

    public void LogEvent(T logEvent, LogLevel level = LogLevel.Information)
    {
        // Destructure the event into its properties using Serilog's @ operator
        _logger.Log(
            level,
            "{@Event}",
            logEvent);

        // Emit schema metadata as a separate structured scope
        // so schema info is always queryable independently of payload
        using var _ = _logger.BeginScope(new Dictionary<string, object>
        {
            ["schema.namespace"] = logEvent.Schema.Namespace,
            ["schema.version"] = logEvent.Schema.Version,
            ["schema.compatibility"] = logEvent.Schema.Compatibility.ToString(),
            ["event.type"] = logEvent.EventType,
            ["event.id"] = logEvent.EventId
        });
    }
}
```

Usage at the call site is then just:

```csharp
_eventLogger.LogEvent(new PaymentProcessedEvent
{
    OrderId = order.Id,
    Provider = result.Provider,
    Amount = order.TotalAmount,
    Currency = order.Currency,
    DurationMs = stopwatch.ElapsedMilliseconds,
    Status = "completed"
});
```

The call site does not repeat field names, does not pass raw strings, and cannot forget the schema metadata — it is part of the type.

## Versioning Your Schemas Across Time

When the schema changes, the version changes with it. The convention to follow:

{{< mermaid >}}
flowchart TD
    change["Schema change"]
    type{"Change type?"}
    add_opt["Add optional field"]
    remove["Remove a field"]
    add_req["Add required field"]
    rename["Rename a field"]
    retype["Change field type"]
    patch["Patch bump · 1.0.x<br/>BackwardCompatible"]
    fwd["Minor bump · 1.x.0<br/>ForwardCompatible"]
    major["Major bump · x.0.0<br/>Breaking — dual-emit"]
    change --> type
    type --> add_opt --> patch
    type --> remove --> fwd
    type --> add_req --> major
    type --> rename --> major
    type --> retype --> major
    style patch fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
    style fwd fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF
    style major fill:#2A0A0A,stroke:#CC4444,color:#FF6060
{{< /mermaid >}}

| Change type | Version bump | Compatibility |
|-------------|-------------|---------------|
| Add optional field | Patch (1.0.x) | BackwardCompatible |
| Add required field | Major (x.0.0) | Breaking |
| Rename a field | Major (x.0.0) | Breaking |
| Change a field type | Major (x.0.0) | Breaking |
| Remove a field | Minor (1.x.0) | ForwardCompatible for readers that don't use the field; Breaking for those that do |

For breaking changes, run both schema versions in parallel during the migration window. This means your event class emits both the old and new field name simultaneously:

```csharp
public record PaymentProcessedEvent_V3 : VersionedLogEvent
{
    public PaymentProcessedEvent_V3()
    {
        Schema = new SchemaInfo
        {
            Namespace = "com.myorg.payments",
            Version = "3.0.0",
            Compatibility = CompatibilityLevel.Breaking
        };
        EventType = "payment.processed";
    }

    // V3 renames duration_ms to latency_ms
    // Emit both during migration; remove duration_ms once consumers are updated
    public int LatencyMs { get; init; }

    [Obsolete("Renamed to LatencyMs in v3.0.0. Will be removed in v4.0.0.")]
    public int DurationMs => LatencyMs;  // read-only alias during migration

    public string OrderId { get; init; } = string.Empty;
    public string Provider { get; init; } = string.Empty;
    public decimal Amount { get; init; }
    public string Currency { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;
}
```

The `[Obsolete]` attribute triggers compile-time warnings for internal consumers of the event type — a nudge that turns migration from a background task into something the compiler actively reminds you about.

## Detecting Schema Drift at Runtime

Schema versioning metadata is only useful if something reads it. A simple validation middleware can check incoming log events against a registry of known schema versions:

```csharp
public class SchemaValidator
{
    private readonly Dictionary<string, HashSet<string>> _knownVersions = new()
    {
        ["com.myorg.payments"] = ["1.0.0", "2.0.0", "2.1.0", "3.0.0"],
        ["com.myorg.orders"] = ["1.0.0", "1.1.0", "2.0.0"],
        ["com.myorg.users"] = ["1.0.0"]
    };

    public SchemaValidationResult Validate(VersionedLogEvent logEvent)
    {
        var schema = logEvent.Schema;

        if (!_knownVersions.TryGetValue(schema.Namespace, out var versions))
            return SchemaValidationResult.UnknownNamespace(schema.Namespace);

        if (!versions.Contains(schema.Version))
            return SchemaValidationResult.UnknownVersion(schema.Namespace, schema.Version);

        return SchemaValidationResult.Valid();
    }
}
```

Deploy this as a validation layer in your Collector pipeline using an OTTL processor, and emit a metric when unknown schema versions appear. That metric is your early warning system for schema drift — a service upgraded with a new schema version but without a corresponding registry update shows up as an anomaly within minutes of deployment, not weeks later when a dashboard mysteriously stops refreshing.

## Where Schema Metadata Lives in Your Pipeline

Schema fields propagate through your log pipeline as regular structured properties. Your log aggregator (Grafana Loki, OpenSearch, Splunk) indexes them like any other field:

```
schema.namespace = "com.myorg.payments"
schema.version = "2.1.0"
event.type = "payment.processed"
```

This makes schema version a first-class query dimension. You can ask:

- "How many events from schema version 2.0.0 are still arriving? (Should be zero — we deprecated it last sprint.)"
- "Are all payment events on version 2.1.0 or later? Show me anything older."
- "When did we start seeing version 3.0.0 events in production? Was it before or after the incident?"

The third question is the one that makes schema versioning worth the effort. When you are debugging a regression, knowing exactly when a schema changed — and being able to correlate that change with a behaviour change — is the difference between a hunch and evidence.

Your logs have always had a schema. Versioning makes that schema visible, queryable, and enforceable — which is the only way to keep it honest over time.

<!-- TODO: Add section on using Confluent Schema Registry with log schemas (non-Kafka use) -->
<!-- TODO: Add section on auto-generating schema metadata from C# source at build time -->
<!-- TODO: Cross-reference to structured-logging-machine-readable.md for the foundational structured logging concepts -->
