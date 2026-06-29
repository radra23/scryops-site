---
title: "Log Context Enrichment: Adding Meaning to Your Events"
date: 2026-06-11
draft: true
excerpt: "Enrichment turns isolated log records into connected business events. Here is the architecture that makes it work — static resource attributes, background-refreshed caches, and real-time scope propagation — without taxing the request path."
readtime: 9
tags: ["Logs", "Observability", "OpenTelemetry", "Structured Logging", "Best Practices"]
---

A log line that reads `"Payment failed"` tells you something went wrong. A log line that reads `"Payment failed"` with `customer_tier=enterprise`, `order_value_range=high`, `region=EU`, and `retry_count=3` tells you something actionable. Enrichment is the difference between knowing an event occurred and knowing what it means.

The challenge is doing it without adding latency to every request. Enrichment that calls a database on each log event is not enrichment — it is a way to turn a payment failure into a timeout cascade under load. The architecture that avoids this splits enrichment into three tiers, each with a different source of data and a different integration point.

## The Three Tiers

| Tier | Changes how often | Source | .NET mechanism |
|---|---|---|---|
| Static | Never (per deployment) | Config, environment, build metadata | OTel `ResourceBuilder` |
| Cached | Minutes to hours | External lookups pre-fetched in background | `EnrichmentCache` + `BackgroundService` |
| Real-time | Per request | In-process state: Activity, scope, request context | `ILogger.BeginScope`, `Activity.Current` |

The governing rule: **no enricher ever calls an external service synchronously.** Static data is set once at startup. Cached data is fetched asynchronously in a background service and read synchronously by enrichers. Real-time data is already in-process.

## Tier 1: Static Enrichment

Service name, version, environment, deployment region — these do not change while the service is running. OTel's `ResourceBuilder` is the right place for static enrichment. Resource attributes propagate automatically to every log record, trace, and metric the service exports.

```csharp
var resourceBuilder = ResourceBuilder.CreateDefault()
    .AddService(
        serviceName: configuration["ServiceName"]!,
        serviceVersion: configuration["ServiceVersion"]!)
    .AddAttributes(new Dictionary<string, object>
    {
        ["deployment.environment"] = configuration["Environment"]!,
        ["deployment.region"]      = configuration["Region"]!,
        ["team.name"]              = configuration["TeamName"]!,
    });
```

Note: in the .NET SDK, pass the service version as a string argument to `AddService()` or as the `"service.version"` string key in `AddAttributes()`. The `SERVICE_VERSION` constant exported by the Python SDK does not exist in the .NET SDK.

For static enrichment, `ResourceBuilder` is the complete answer. There is no pipeline, no cache, no background service required.

## Tier 2: Cached Enrichment

Customer tier, feature flag assignments, A/B cohorts — these change infrequently but require a lookup to retrieve. The pattern: fetch asynchronously in a background service, store in memory, read synchronously at log time.

### TTL by Data Volatility

Not all cached data ages at the same rate. Expressing TTLs as volatility categories keeps configuration readable:

```csharp
public enum DataVolatility
{
    Static,               // Config values: rarely changes
    SlowChanging,         // User tier, subscription status: changes over days
    ModeratelyChanging,   // Feature flags, A/B assignments: changes over hours
    FastChanging          // Rate-limit state, session counters: changes over minutes
}
```

A two-tier cache — in-process memory backed by a distributed store — lets enrichers read at memory speed on cache hits while surviving process restarts with warm distributed state:

```csharp
public class EnrichmentCache
{
    private readonly IMemoryCache      _memory;
    private readonly IDistributedCache _distributed;

    public async Task<T?> GetOrSetAsync<T>(
        string                           key,
        Func<CancellationToken, Task<T>> factory,
        DataVolatility                   volatility,
        CancellationToken                ct = default)
    {
        // L1: in-process memory (fastest, no serialisation)
        if (_memory.TryGetValue(key, out T? hit)) return hit;

        // L2: distributed cache (survives restart, shared across replicas)
        var bytes = await _distributed.GetAsync(key, ct);
        if (bytes is not null)
        {
            var cached = Deserialize<T>(bytes);
            _memory.Set(key, cached, MemoryTtl(volatility));
            return cached;
        }

        // Miss: fetch from source, populate both tiers
        var value = await factory(ct);
        if (value is not null)
        {
            await _distributed.SetAsync(
                key,
                Serialize(value),
                new DistributedCacheEntryOptions
                {
                    AbsoluteExpirationRelativeToNow = DistributedTtl(volatility)
                },
                ct);
            _memory.Set(key, value, MemoryTtl(volatility));
        }
        return value;
    }

    private static TimeSpan MemoryTtl(DataVolatility v) => v switch
    {
        DataVolatility.Static             => TimeSpan.FromHours(1),
        DataVolatility.SlowChanging       => TimeSpan.FromMinutes(30),
        DataVolatility.ModeratelyChanging => TimeSpan.FromMinutes(5),
        DataVolatility.FastChanging       => TimeSpan.FromMinutes(1),
        _                                 => TimeSpan.FromMinutes(5)
    };

    private static TimeSpan DistributedTtl(DataVolatility v) => v switch
    {
        DataVolatility.Static             => TimeSpan.FromDays(1),
        DataVolatility.SlowChanging       => TimeSpan.FromHours(4),
        DataVolatility.ModeratelyChanging => TimeSpan.FromMinutes(30),
        DataVolatility.FastChanging       => TimeSpan.FromMinutes(5),
        _                                 => TimeSpan.FromMinutes(30)
    };
}
```

### Background Refresh

A `BackgroundService` pre-warms the cache at startup and periodically refreshes data before TTLs expire. `PeriodicTimer` (available since .NET 6) avoids the drift accumulation that `Task.Delay` in a while loop produces over hours.

```csharp
public class EnrichmentCacheWarmup : BackgroundService
{
    private readonly EnrichmentCache      _cache;
    private readonly IEnrichmentDataSource _source;
    private readonly ILogger<EnrichmentCacheWarmup> _logger;

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        // Warm up at startup so enrichers have data immediately
        await RefreshAsync(ct);

        // Refresh on a schedule shorter than the shortest TTL
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(4));
        while (await timer.WaitForNextTickAsync(ct))
            await RefreshAsync(ct);
    }

    private async Task RefreshAsync(CancellationToken ct)
    {
        try
        {
            var data = await _source.FetchEnrichmentDataAsync(ct);
            foreach (var entry in data)
                await _cache.GetOrSetAsync(entry.Key, _ => Task.FromResult(entry.Value),
                    entry.Volatility, ct);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Log but do not crash the background service — stale cache is better than no cache
            _logger.LogWarning("Enrichment cache refresh failed: {ErrorType}", ex.GetType().Name);
        }
    }
}
```

At log time, enrichers read from the in-process cache synchronously. The async work is entirely confined to the background service.

## Tier 3: Real-Time Enrichment

Request ID, trace ID, authenticated user ID, operation name — these are available in-process without any lookup. They belong in `ILogger.BeginScope` (MEL) or as Serilog enrichers reading from `Activity.Current`.

With MEL — set in middleware once per request:

```csharp
public class LogContextMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<LogContextMiddleware> _logger;

    public async Task InvokeAsync(HttpContext context)
    {
        // BeginScope runs once per request, not per log call
        using (_logger.BeginScope(new Dictionary<string, object?>
        {
            ["TraceId"]    = Activity.Current?.TraceId.ToString(),
            ["RequestId"]  = context.TraceIdentifier,
            ["UserId"]     = context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value,
            ["UserTier"]   = _cache.GetUserTier(context.User.FindFirst("sub")?.Value),
        }))
        {
            await _next(context);
        }
    }
}
```

With Serilog — as an `ILogEventEnricher` registered at application startup:

```csharp
public class ActivityEnricher : ILogEventEnricher
{
    public void Enrich(LogEvent logEvent, ILogEventPropertyFactory factory)
    {
        var activity = Activity.Current;
        if (activity is null) return;

        logEvent.AddPropertyIfAbsent(
            factory.CreateProperty("TraceId", activity.TraceId.ToString()));
        logEvent.AddPropertyIfAbsent(
            factory.CreateProperty("SpanId", activity.SpanId.ToString()));
        logEvent.AddPropertyIfAbsent(
            factory.CreateProperty("ParentSpanId", activity.ParentSpanId.ToString()));
    }
}
```

Both read from thread-local state. No cache, no I/O.

## Orchestrating Multiple Enrichment Providers

When you have several enrichment providers, a pipeline applies them in priority order, skipping those that do not apply, and stopping when the time budget is exhausted:

```csharp
public interface IEnrichmentProvider
{
    string Name     { get; }
    int    Priority { get; }  // Lower value = higher priority, runs first
    bool   AppliesTo(object logEvent, EnrichmentContext context);
    Task<IReadOnlyDictionary<string, object?>?> EnrichAsync(
        object logEvent, EnrichmentContext context, CancellationToken ct);
}

public record EnrichmentContext(
    TimeSpan? PerformanceBudget = null,
    string?   CorrelationId    = null);

public class EnrichmentPipeline
{
    private readonly IReadOnlyList<IEnrichmentProvider> _providers;

    public EnrichmentPipeline(IEnumerable<IEnrichmentProvider> providers)
    {
        _providers = providers.OrderBy(p => p.Priority).ToList();
    }

    public async Task<IReadOnlyDictionary<string, object?>> EnrichAsync(
        object logEvent, EnrichmentContext context)
    {
        var merged   = new Dictionary<string, object?>();
        var budget   = context.PerformanceBudget ?? TimeSpan.FromMilliseconds(50);
        var started  = Stopwatch.GetTimestamp();

        foreach (var provider in _providers)
        {
            var elapsed = Stopwatch.GetElapsedTime(started);
            if (elapsed >= budget) break;

            if (!provider.AppliesTo(logEvent, context)) continue;

            var remaining = budget - elapsed;
            try
            {
                using var cts = new CancellationTokenSource(remaining);
                var result = await provider.EnrichAsync(logEvent, context, cts.Token);
                if (result is not null)
                    foreach (var (k, v) in result) merged[k] = v;
            }
            catch (OperationCanceledException)
            {
                // Provider exceeded its share of the budget; skip and continue
            }
            catch (Exception)
            {
                // Provider failed; do not surface to caller
            }
        }

        return merged;
    }
}
```

The `Priority` ordering ensures critical, lightweight enrichers (static context, in-process state) run first. Lower-priority enrichers (heavier cache lookups) only run if budget remains.

{{< insight lightbulb >}}
**The critical invariant:** enrichers must not perform I/O. All external data must come from the `EnrichmentCache`. An enricher that calls a database or external service directly will add the latency of that call to every log statement it affects — and under load, will cause those calls to queue up behind each other.
{{< /insight >}}

## Runtime and Infrastructure Context

One category of enrichment sits outside the tier model: dynamic runtime state that is already in-process and requires no external lookup. GC pressure, thread pool utilisation, and process uptime are useful at diagnostic boundaries — when correlating a slow request path with a Gen 2 collection, or confirming that a timeout happened while the thread pool was already saturated.

`RuntimeContextSnapshot.Capture()` produces a dictionary suitable for `BeginScope`:

```csharp
/// <summary>
/// Captures a point-in-time snapshot of runtime state for diagnostic context.
/// Use at error or slow-path boundaries — not on every log event.
/// </summary>
public static class RuntimeContextSnapshot
{
    public static Dictionary<string, object> Capture()
    {
        ThreadPool.GetAvailableThreads(
            out int availableWorker, out int availableIocp);
        ThreadPool.GetMaxThreads(
            out int maxWorker, out int maxIocp);

        return new Dictionary<string, object>
        {
            ["runtime.gc.total_memory_bytes"] = GC.GetTotalMemory(forceFullCollection: false),
            ["runtime.gc.gen0_collections"]   = GC.CollectionCount(0),
            ["runtime.gc.gen1_collections"]   = GC.CollectionCount(1),
            ["runtime.gc.gen2_collections"]   = GC.CollectionCount(2),
            ["runtime.threadpool.worker_in_use"]  = maxWorker - availableWorker,
            ["runtime.threadpool.worker_max"]     = maxWorker,
            ["runtime.threadpool.iocp_in_use"]    = maxIocp - availableIocp,
            ["host.name"]         = Environment.MachineName,
            ["host.platform"]     = Environment.OSVersion.Platform.ToString(),
            ["process.id"]        = Environment.ProcessId,
            ["process.uptime_ms"] = Environment.TickCount64,
        };
    }
}
```

Use it as a `BeginScope` payload at exception boundaries where multiple log calls may follow:

```csharp
catch (Exception ex)
{
    using (_logger.BeginScope(RuntimeContextSnapshot.Capture()))
    {
        _logger.LogError(ex,
            "Critical failure in {Operation} after {DurationMs}ms",
            operationName, stopwatch.ElapsedMilliseconds);
    }
}
```

Deployment metadata (region, zone, build version) should come from static Tier 1 enrichment, not from `Environment.GetEnvironmentVariable()` calls inside `Capture()`. Read those values once at startup and include them in the `ResourceBuilder`.

### OTel Baggage for Cross-Service Correlation

When a caller sets values on the OTel Baggage, they propagate through every outbound call via the W3C `baggage` header and are available in downstream services without custom propagation code:

```csharp
using var scope = _logger.BeginScope(new Dictionary<string, object?>
{
    ["correlation.request_id"] = Baggage.Current.GetBaggage("request_id"),
    ["correlation.tenant_id"]  = Baggage.Current.GetBaggage("tenant_id"),
    ["correlation.user_tier"]  = Baggage.Current.GetBaggage("user_tier"),
});
```

`GetBaggage` returns `null` when the key is absent — the scope entry is included with a null value, which most sinks drop gracefully. Keep Baggage keys to lightweight correlation identifiers and routing hints, not large payloads.

<!-- TODO: Add example implementations of concrete IEnrichmentProvider classes: UserTierEnricher (reads from EnrichmentCache), FeatureFlagEnricher (reads from distributed feature flag store via cache), BusinessContextEnricher (order value buckets, not raw amounts or PII) -->
<!-- TODO: Add Serilog ILogEventEnricher integration showing how to wire EnrichmentPipeline into the Serilog pipeline as a registered enricher -->
<!-- TODO: Add BenchmarkDotNet measurements comparing enrichment overhead by tier — static Resource attributes (near-zero), cached hit path (sub-microsecond), cached miss path (measured separately to separate background refresh cost from hot path cost) -->

## See Also

- [Logging Foundations](/guides/logging-foundations/) — log levels, output format, and the baseline structure enrichment adds context to
- [Structured Logging in .NET](/howtos/implement-structured-logging-dotnet/) — the ILogger and Serilog patterns enrichment integrates with
- [OTel Resource Attributes and Service Naming](/guides/otel-resource-attributes-and-service-naming/) — the authoritative guide to static enrichment via ResourceBuilder
- [High-Throughput Logging](/guides/high-throughput-logging/) — enrichment overhead at scale: where the per-record costs actually land
