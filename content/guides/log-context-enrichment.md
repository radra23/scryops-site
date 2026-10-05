---
title: "Log Context Enrichment: Adding Meaning to Your Events"
date: 2026-06-11
draft: false
excerpt: "Enrichment turns isolated log records into connected business events. Here is the architecture that makes it work — static resource attributes, background-refreshed caches, and per-request scopes — without taxing the request path."
readtime: 8
tags: ["Logs", "Observability", "OpenTelemetry", "Structured Logging", "Best Practices"]
card:
  title: "Log Context Enrichment"
---

A log line that reads `"Payment failed"` tells you something went wrong. The same line with `customer.tier=enterprise`, `cloud.region=eu-west-1` and `retry.count=3` tells you who is hurting, where, and how hard the system already tried. Enrichment is the difference between knowing an event occurred and knowing what it means.

The catch is doing it without adding latency to every request. Enrichment that calls a database on each log event isn't enrichment. It's a way to turn a payment failure into a timeout cascade under load. The architecture that avoids this splits enrichment into three tiers, each with its own data source and its own integration point.

This guide assumes your logs are already structured and that trace IDs already reach them. If not, start with [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/) for field names and [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) for correlation. The examples are .NET, where the OpenTelemetry logs SDK is stable; the patterns carry to any runtime.

## The Three Tiers

| Tier | Changes how often | Source | .NET mechanism |
|---|---|---|---|
| Static | Never (per deployment) | Config, environment, build metadata | OpenTelemetry resource |
| Cached | Minutes to hours | External lookups, fetched in the background | Snapshot cache + `BackgroundService` |
| Per-request | Every request | In-process state: route, tenant, current activity | `ILogger.BeginScope` |

The governing rule: **nothing on the logging path does I/O.** Static data is set once at startup. Cached data is fetched asynchronously by a background service and read synchronously at log time. Per-request data is already in memory.

## Tier 1: Static Enrichment

Service name, version, environment and region don't change while the process runs. They belong on the OpenTelemetry **resource**, which describes the entity producing the telemetry. The SDK attaches it to every batch it exports, so logs, traces and metrics all carry the same identity without a single field on any log call.

```csharp
builder.Services.AddOpenTelemetry()
    .ConfigureResource(resource => resource
        .AddService(
            serviceName: "checkout-api",
            serviceVersion: builder.Configuration["Build:Version"])
        .AddAttributes(new Dictionary<string, object>
        {
            ["deployment.environment.name"] = builder.Environment.EnvironmentName.ToLowerInvariant(),
            ["cloud.region"] = builder.Configuration["Region"] ?? "unknown",
            ["team.name"]    = "payments", // your own key, not a semantic convention
        }))
    .WithLogging(
        logging => logging.AddOtlpExporter(),
        options => options.IncludeScopes = true); // Tier 3 needs this; see below
```

Use the semantic-convention names where they exist. The environment key is `deployment.environment.name`; the older `deployment.environment` is deprecated. Region is `cloud.region`. Anything that isn't in the conventions, like `team.name`, is yours to name, so namespace it and keep it consistent across services.

You can also set all of this without code. Every OpenTelemetry SDK reads two standard environment variables:

```bash
OTEL_SERVICE_NAME=checkout-api
OTEL_RESOURCE_ATTRIBUTES=service.version=1.4.2,deployment.environment.name=production,cloud.region=eu-west-1
```

There is no `OTEL_SERVICE_VERSION` variable; the version goes in `OTEL_RESOURCE_ATTRIBUTES` like everything else. In .NET, the default resource reads both variables, and an attribute you also set in code takes the code's value. Pick one source per key so nobody has to work out which won.

One limit to know: the resource travels with OTLP exports. A JSON console log scraped from stdout doesn't carry it, so for that path the Collector has to add it back. Its `resourcedetection` and `k8sattributes` processors stamp host, cloud and Kubernetes metadata onto every record that passes through. [Log-Based Monitoring](/guides/log-based-monitoring/) shows a Collector `transform` pipeline doing the same kind of work.

## Tier 2: Cached Enrichment

Customer tier, plan, feature-flag cohort: this data changes slowly but lives somewhere else. Fetch it in the background, hold it in memory, read it synchronously at log time.

The simplest version that's correct is an immutable snapshot that gets swapped whole:

```csharp
public sealed class TenantTierCache
{
    private volatile FrozenDictionary<string, string> _tiers =
        FrozenDictionary<string, string>.Empty;

    // Hot path: one dictionary read. No I/O, no await, no lock.
    public string? GetTier(string tenantId) =>
        _tiers.TryGetValue(tenantId, out var tier) ? tier : null;

    // Called only by the refresher. Swapping a reference is atomic.
    public void Replace(IReadOnlyDictionary<string, string> tiers) =>
        _tiers = tiers.ToFrozenDictionary();
}

public sealed class TenantTierRefresher(
    TenantTierCache cache,
    ITenantDirectory directory,
    ILogger<TenantTierRefresher> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(5));
        do
        {
            try
            {
                cache.Replace(await directory.GetTenantTiersAsync(ct));
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                // Keep the last good snapshot: stale context beats no context.
                logger.LogWarning(ex, "Tenant tier refresh failed; keeping previous snapshot");
            }
        }
        while (await timer.WaitForNextTickAsync(ct));
    }
}
```

Register both with `AddSingleton<TenantTierCache>()` and `AddHostedService<TenantTierRefresher>()`. A few properties are doing the real work here:

- **Readers never wait.** A lookup is a read from a frozen dictionary. A miss returns `null` and the field is simply absent; it never triggers a fetch.
- **Failure degrades, it doesn't break.** If the directory is down, logs keep the last known tiers. Logging the failure as a warning, with the exception attached, tells you the context is going stale.
- **`PeriodicTimer` keeps a steady cadence.** Its ticks don't shift by the time each refresh takes, which a `Task.Delay` loop does.
- **The refresh interval is your staleness budget.** Five minutes means a tenant who upgrades can be logged as their old tier for up to five minutes. Choose the interval per data source with that in mind.

Two caveats. The first refresh runs after the host starts, so the earliest requests may log without a tier. If that matters, load the first snapshot before the app starts accepting traffic. And a full snapshot only works when the data set fits comfortably in memory, as tenant or plan tables usually do. For large per-key data, keep the same shape: a synchronous read of whatever is already cached, with misses queued for the background to fetch, never awaited inline.

## Tier 3: Per-Request Enrichment

Some context only exists for the duration of a request: the tenant, the route, the activity. Push it into a logging scope once, in middleware, and every log call inside the request picks it up.

Before adding anything, check what you already get. The ASP.NET Core host opens scopes with `TraceId`, `SpanId`, `ParentId`, `ConnectionId`, `RequestId` and `RequestPath` on every request. Adding a `TraceId` of your own just duplicates it. Your middleware should add only what the framework can't know:

```csharp
var tiers  = app.Services.GetRequiredService<TenantTierCache>();
var logger = app.Services.GetRequiredService<ILogger<Program>>();

app.Use(async (context, next) =>
{
    var tenantId = context.User.FindFirst("tenant_id")?.Value;

    using (logger.BeginScope(new Dictionary<string, object?>
    {
        ["tenant.id"]     = tenantId,
        ["customer.tier"] = tenantId is null ? null : tiers.GetTier(tenantId),
    }))
    {
        await next(context);
    }
});
```

Scopes flow with the async call chain (they live in an `AsyncLocal`, not in thread-local storage), so they survive every `await` inside the request. [Async Logging](/guides/async-logging/) covers the other half: capturing that context when the record is enqueued, not when a background writer gets round to it.

{{< insight >}}
**Scopes are off by default in the OpenTelemetry exporter.** With `IncludeScopes` left at `false`, every scope above, including the host's own `RequestId`, is dropped before export. Your logs look enriched in the console and arrive bare in the backend. Set `options.IncludeScopes = true`, as in the Tier 1 configuration.
{{< /insight >}}

Note what's missing from that scope: the user. A raw user ID, email or name on every log line turns your log store into a personal-data store, with everything that implies for access, retention and erasure requests. A tenant ID is usually fine. If you genuinely need to follow one person's requests, use a keyed pseudonym rather than the raw identifier. [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) explains why plain hashing isn't enough, and [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/) shows the redaction wiring.

### If you use Serilog

Since Serilog 3.1, every event records `Activity.Current`'s trace and span IDs as first-class `TraceId` and `SpanId` properties, so the custom "activity enricher" many codebases still carry is redundant. Per-request business context goes through `LogContext`:

```csharp
// At startup: .Enrich.FromLogContext()
using (LogContext.PushProperty("customer.tier", tier))
{
    Log.Information("Payment failed for {OrderId}", orderId);
}
```

## Runtime State at the Failure Boundary

Some context is worth having only when something has gone wrong. Was the thread pool backed up when this timeout fired? Had there just been a burst of Gen 2 collections? That state is in-process and cheap to read, but not free, so capture it at error and slow-path boundaries rather than on every event:

```csharp
public static class RuntimeSnapshot
{
    // Point-in-time runtime state for error and slow-path boundaries only.
    public static Dictionary<string, object> Capture() => new()
    {
        ["diag.gc.heap_bytes"]           = GC.GetTotalMemory(forceFullCollection: false),
        ["diag.gc.gen2_collections"]     = GC.CollectionCount(2),
        ["diag.threadpool.threads"]      = ThreadPool.ThreadCount,
        ["diag.threadpool.queue_length"] = ThreadPool.PendingWorkItemCount,
        ["diag.process.uptime_s"]        = (long)(DateTime.Now - Process.GetCurrentProcess().StartTime).TotalSeconds,
    };
}
```

```csharp
catch (Exception ex)
{
    using (_logger.BeginScope(RuntimeSnapshot.Capture()))
    {
        _logger.LogError(ex, "Payment failed for {OrderId}", orderId);
    }
    return PaymentResult.Failed; // handled here, so logged here; don't rethrow
}
```

The `diag.*` names are deliberately your own namespace. OpenTelemetry does define runtime conventions, but as metrics (`dotnet.gc.collections`, `dotnet.thread_pool.queue.length` and friends), and those metrics are the better home for trends. The snapshot answers a narrower question: what did the runtime look like at the moment this particular request failed? Host name, process ID and region don't belong here either. They're static, so they go on the resource in Tier 1.

## Carrying Context Across Services with Baggage

A tenant resolved at the edge is useful three services downstream, too. OpenTelemetry **baggage** carries key-value pairs alongside the trace context in the W3C `baggage` header. With the ASP.NET Core and `HttpClient` instrumentation installed, incoming baggage lands in `Baggage.Current` and outgoing calls carry it on.

Baggage does not turn into log attributes on its own. Each service copies the keys it wants into its scope:

```csharp
using var scope = _logger.BeginScope(new Dictionary<string, object?>
{
    ["tenant.id"] = Baggage.GetBaggage("tenant.id"),
});
```

Treat baggage as public. It travels in plain HTTP headers to every downstream call, including third-party APIs, and nothing verifies who set it. Keep it to small, non-sensitive routing keys like a tenant ID or a region. No user identifiers, no tokens, nothing you'd mind seeing in someone else's access log.

## Where to Spend the Effort

Enrichment pays off when the fields it adds are the ones your queries group by: tier, tenant, region, version. Start with the resource, since it's one block of configuration and every signal benefits. Add a request scope for the two or three business fields your incident reviews keep asking about. Reach for cached lookups only when a field genuinely lives in another system.

Every field you add is also a field you store and index on every event. [High-Throughput Logging](/guides/high-throughput-logging/) covers where those per-record costs land, and [Common Logging Pitfalls](/guides/common-logging-pitfalls/) covers the naming drift that makes enriched fields hard to query across teams.

## See Also

- [Logging Foundations](/guides/logging-foundations/) — what logs are for, and the baseline structure enrichment adds context to
- [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/) — the field names enrichment should reuse
- [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) — trace correlation, which most runtimes now attach for you
- [Distributed Logging](/guides/distributed-logging/) — collecting and correlating logs across many services
- [Log-Based Monitoring](/guides/log-based-monitoring/) — turning enriched fields into queries, metrics and alerts
- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — what not to enrich with
