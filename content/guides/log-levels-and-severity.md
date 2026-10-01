---
title: "Log Levels: When to Whisper, Speak, or Shout"
date: 2026-10-01
draft: false
excerpt: "Log levels are the emotional register of your system's voice. How to use ERROR, WARN, INFO, DEBUG and TRACE consistently, how they map onto OpenTelemetry's severity numbers, and what each one costs you."
readtime: 12
tags: ["Logs", "Observability", "Best Practices"]
---

It's 3am, the pager just went off, and you're scrolling a wall of logs where a routine startup trace sits right next to the payment failure that actually woke you. Nothing tells them apart, so neither gets the response it deserves. That is what log levels are for: a contract between the code that emits a log and the person — or system — that has to read it under pressure.

## One Scale, Many Dialects

Every logging framework has levels, and no two spell them the same way. Two reference scales sit underneath them.

The older one is **RFC 5424**, the IETF syslog standard. It defines eight severities numbered 0–7, with 0 the most severe:

| Level | Name | Meaning | Example |
|-------|------|---------|---------|
| 0 | Emergency | System unusable | Total system failure |
| 1 | Alert | Action required immediately | Security breach detected |
| 2 | Critical | Critical conditions | Primary database down |
| 3 | Error | Error conditions | Payment processing failed |
| 4 | Warning | Warning conditions | Retry needed to succeed |
| 5 | Notice | Normal but significant | Configuration changed |
| 6 | Informational | Informational messages | Order completed |
| 7 | Debug | Debug-level messages | Branch taken, values used |

The one that matters for anything flowing through OpenTelemetry is the log data model's **`SeverityNumber`**. It runs the other way, from 1 (least severe) to 24, in six ranges of four. Each language bridge maps its own levels onto the first number of each range:

| OTel range | `SeverityNumber` | .NET `LogLevel` | Java (SLF4J) | Go `slog` | Python `logging` |
|---|---|---|---|---|---|
| TRACE | 1–4 | `Trace` | `TRACE` | — | — |
| DEBUG | 5–8 | `Debug` | `DEBUG` | `Debug` (−4) | `DEBUG` (10) |
| INFO | 9–12 | `Information` | `INFO` | `Info` (0) | `INFO` (20) |
| WARN | 13–16 | `Warning` | `WARN` | `Warn` (4) | `WARNING` (30) |
| ERROR | 17–20 | `Error` | `ERROR` | `Error` (8) | `ERROR` (40) |
| FATAL | 21–24 | `Critical` | — | — | `CRITICAL` (50) |

Query and alert on `SeverityNumber`, not on the text. `severity_number >= 17` finds every error from every service, whatever the service wrote in `SeverityText`: `Error`, `ERROR`, `error` or `err`. The finer steps inside each range (`INFO2`, `WARN3`) exist for frameworks with more levels than six. Most code never needs them.

## ERROR — The Operation Failed

ERROR means the operation failed and a human needs to know. It should be rare enough that every occurrence deserves attention. If an operator sees an ERROR and has no clear next step, either the log lacks context or the level is wrong.

Use ERROR when a failure affects a user or breaks a business process: a payment that didn't go through, a dependency that returned an unrecoverable status, data that couldn't be written. Don't use it for expected outcomes like a wrong password or a declined card. Those are the application working as designed, and logging them at ERROR trains everyone to ignore ERROR.

**Use ERROR for:**
- Failures that affect a user or a business process
- Lost connections to a dependency the request needed
- Integration failures with external services
- Data that could not be persisted or was rejected as corrupt

**A good ERROR log:**
```json
{
  "timestamp": "2026-05-21T13:45:30Z",
  "severity_text": "ERROR",
  "severity_number": 17,
  "service.name": "payment-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event.name": "payment.failed",
  "message": "Payment failed: gateway timeout after 30s and 3 retries",
  "error.type": "gateway_timeout",
  "payment.provider": "stripe",
  "payment.retry_count": 3,
  "order.id": "ord_12345",
  "order.value": 299.99,
  "customer.tier": "premium",
  "customer.ref": "36bb095813943f38"
}
```

It answers what failed, why, for which request and for whom. The customer is a pseudonymous reference, not an ID or an email; see [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) for why.

**FATAL / CRITICAL** sits above ERROR for the cases where the process itself can't continue: a missing required configuration value at startup, or corrupted state the service refuses to run with. If the service carries on serving traffic afterwards, it wasn't FATAL.

## WARN — Degraded but Not Broken

WARN signals that something is wrong but the system is still working. The operation succeeded, or recovered, but in a way that may not hold. The difference from ERROR is operational: an ERROR needs investigating now, a WARN needs investigating before it turns into an ERROR.

Good WARN logs can be acted on during working hours. A retry that eventually succeeded, a fallback that served stale data, a call to an API that's being retired: these belong at WARN. Left alone they become errors; handled early, they never do.

**Use WARN for:**
- Operations that succeeded only after retries or a fallback
- Deprecated features or APIs still in use
- Configuration that's wrong but survivable
- Inputs rejected by validation in volumes that suggest a broken client

**A good WARN log:**
```json
{
  "timestamp": "2026-05-21T13:45:30Z",
  "severity_text": "WARN",
  "severity_number": 13,
  "service.name": "inventory-service",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331",
  "event.name": "inventory.reserve.retried",
  "message": "Stock reservation succeeded after 2 retries (warehouse API 503)",
  "retry.count": 2,
  "retry.total_wait_ms": 1400,
  "upstream.name": "warehouse-api",
  "http.response.status_code": 503
}
```

What WARN is *not* for is resource levels. "Memory at 85%" is a measurement, and measurements belong in metrics, where they can be graphed, compared over time and alerted on with a threshold you can change without redeploying. A log line per crossing is a poor copy of a metric.

## INFO — Significant Events in Normal Operation

INFO records events that matter for understanding what the system did, without recording every step of how it did it. A completed order, a user signing in, a configuration reload: these belong at INFO. Someone reading only the INFO logs should get a coherent picture of system activity without drowning in implementation detail.

The test: would you want this event in a summary of what happened today? If yes, it's INFO. If it fires dozens of times a second under normal load, it's probably too frequent for INFO unless each one genuinely matters. High-volume INFO is where most log bills come from; [sampling](#sampling-high-frequency-events) is covered below.

**Use INFO for:**
- Business operations that completed
- State changes and lifecycle events (startup, shutdown, config reload, leadership change)
- User actions with business significance

**A good INFO log:**
```json
{
  "timestamp": "2026-05-21T13:45:30Z",
  "severity_text": "INFO",
  "severity_number": 9,
  "service.name": "order-service",
  "trace_id": "5b8efff798038103d269b633813fc60c",
  "span_id": "eee19b7ec3c1b174",
  "event.name": "order.completed",
  "message": "Order ord_12345 completed: payment captured, stock reserved, customer notified",
  "order.id": "ord_12345",
  "order.value": 299.99,
  "customer.tier": "premium",
  "duration_ms": 847
}
```

## DEBUG — Why the Code Did What It Did

DEBUG captures the internal state and decision points that explain why the system behaved as it did: values used, branches taken, intermediate results. It's off in production by default because of its volume. Turn it on for one service or one component while you investigate, then turn it off again; [changing levels at runtime](#changing-levels-at-runtime) shows how.

A DEBUG log should answer "why did this code take this path?" If you find yourself turning on DEBUG just to understand normal operation, your INFO logs need work.

**Use DEBUG for:**
- Decision points and the values that drove them
- Feature-flag evaluations and which variant was served
- Choices an algorithm made, and why

**A good DEBUG log:**
```json
{
  "timestamp": "2026-05-21T13:45:30Z",
  "severity_text": "DEBUG",
  "severity_number": 5,
  "service.name": "payment-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event.name": "payment.gateway.selected",
  "message": "Selected gateway stripe: lowest fee for tier premium; adyen skipped (circuit open)",
  "payment.provider": "stripe",
  "selection.reason": "lowest_fee_for_tier",
  "selection.skipped": ["adyen"],
  "feature_flag.key": "premium-fast-track",
  "feature_flag.result.variant": "on"
}
```

## TRACE — Step-by-Step Execution

TRACE records execution step by step: method entry and exit, loop iterations, fine-grained timing. It's the noisiest level and belongs only in development or a short, targeted session. If you leave TRACE on in production, it buries the signal you're looking for.

Before reaching for TRACE, check whether a span would answer the question better. Entry, exit and duration of an operation are exactly what tracing records, with the parent-child structure that a stream of log lines loses.

**A good TRACE log:**
```json
{
  "timestamp": "2026-05-21T13:45:30Z",
  "severity_text": "TRACE",
  "severity_number": 1,
  "service.name": "payment-api",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "ValidatePayment: checksum ok, calling gateway",
  "code.function.name": "PaymentValidator.ValidatePayment",
  "step": "gateway_call",
  "elapsed_us": 1247
}
```

## A Log Level Is Not an Incident Severity

It's tempting to page on ERROR logs. Don't. A log level describes one event in one process. An [incident severity](/guides/alert-severity-levels/) describes the impact on users, and that is better measured by an SLO burn rate than by a count of lines. A single ERROR during a dependency blip is normal. A thousand ERRORs from a batch job nobody depends on may not matter. A silent outage may produce no ERRORs at all. Use ERROR rates to *explain* an alert, and SLOs to *raise* one.

## Cost: Route by How Long You'll Need It

DEBUG and TRACE are usually the bulk of raw log lines, so turning them off in production removes most of your volume before it reaches central storage. What's left should be routed by how long you'll need to search it, not by delaying it. INFO is what you use to reconstruct what a user experienced during an incident, so it has to be searchable as soon as the incident starts. Putting INFO in a daily cold batch saves money right up until the outage where you need it.

{{< mermaid caption="Fig. — Every level that ships is searchable immediately; levels differ in how long they are kept and whether high-volume events are sampled. DEBUG and TRACE stay off unless someone turns them on to investigate." >}}
flowchart LR
    A[Log event] --> B{Level}
    B -->|ERROR / FATAL| C[Searchable now<br/>long retention]
    B -->|WARN| D[Searchable now<br/>long retention]
    B -->|INFO| E[Searchable now<br/>shorter retention<br/>sample high-volume events]
    B -.->|DEBUG / TRACE| F[Off in production<br/>on demand, scoped]
{{< /mermaid >}}

Retention periods depend on your incident-review cycle and any compliance obligations; the shape is what matters. A typical starting point is ERROR and WARN kept for the length of your longest incident review plus a margin, and INFO for a week or two. Anything beyond that is aggregated into metrics before the raw lines are dropped.

## Performance: Don't Pay for Logs You Don't Write

A disabled log call is cheap but not free. In .NET, `_logger.LogDebug("Processing {ItemId}", item.Id)` still allocates the argument array and boxes value types before the logger decides the level is off. In a tight loop that adds up. Two fixes:

```csharp
// 1. Guard expensive arguments: BuildDetailedReport() runs even when Debug is disabled.
if (_logger.IsEnabled(LogLevel.Debug))
{
    _logger.LogDebug("Analysis: {@Report}", BuildDetailedReport(order));
}

// 2. For hot paths, let the source generator write the check for you:
//    no boxing, no params array, and the level test happens first.
static partial class Log
{
    [LoggerMessage(Level = LogLevel.Error, Message = "Payment failed for order {OrderId}: {ErrorType}")]
    public static partial void PaymentFailed(ILogger logger, string orderId, string errorType);

    [LoggerMessage(Level = LogLevel.Debug, Message = "Processed item {ItemId}")]
    public static partial void ItemProcessed(ILogger logger, int itemId);
}
```

The same idea exists elsewhere. SLF4J's `{}` placeholders defer formatting, and `log.atDebug().addArgument(() -> expensive())` defers computing the value. Python's `logger.debug("x=%s", x)` defers formatting, but not computing `x`. Go's `slog` checks `Enabled` before building the record. For keeping the logging call itself off the request path at very high volumes, see [High-Throughput Logging: Keeping the Hot Path Fast](/guides/high-throughput-logging/).

## Anti-Patterns

These are the logging anti-patterns that turn up most often in production codebases.

### 1. Log-and-Throw
```csharp
// ❌ Logged here, then caught and logged again by every layer above
try
{
    ProcessPayment(order);
}
catch (PaymentException ex)
{
    _logger.LogError(ex, "Payment failed");
    throw;
}

// ✅ Log once, where the exception is handled
try
{
    ProcessPayment(order);
}
catch (PaymentException ex)
{
    _logger.LogError(ex, "Payment failed for order {OrderId}", order.Id);
    return PaymentResult.Failed(ex.Message);
}
```

The rule: either handle the exception and log it, or rethrow it and don't. One failure should produce one ERROR, written by the code that decided what to do about it.

### 2. Exception Swallowing
```csharp
// ❌ Silent failure: nobody knows this happened
try
{
    SendNotification(user);
}
catch
{
}

// ✅ The failure is handled (retried later), so WARN, not ERROR
try
{
    SendNotification(user);
}
catch (Exception ex)
{
    _logger.LogWarning(ex, "Notification for user {UserRef} failed; queued for retry", user.Ref);
}
```

### 3. Flooding
```csharp
// ❌ One line per item in a loop over millions of items
foreach (var item in millionsOfItems)
{
    _logger.LogDebug("Processing item {ItemId}", item.Id);
}

// ✅ Report progress, not every step
var processed = 0;
foreach (var item in millionsOfItems)
{
    if (++processed % 10_000 == 0)
    {
        _logger.LogDebug("Processed {Count} items, current {ItemId}", processed, item.Id);
    }
}
```

## Changing Levels at Runtime

You'll want DEBUG for one component during an investigation without redeploying. In .NET the host already supports this: `appsettings.json` is reloaded when it changes, and the logging filters are re-applied with it. Raise the level for one category, not the whole service:

```json
{
  "Logging": {
    "LogLevel": {
      "Default": "Information",
      "Microsoft.AspNetCore": "Warning",
      "Checkout.Payments": "Debug"
    }
  }
}
```

Logback can rescan its config the same way (`<configuration scan="true">`), Python can change a logger's level at runtime with `logging.getLogger("checkout.payments").setLevel(logging.DEBUG)`, and Go's `slog.LevelVar` can be changed while the program runs. Whichever you use, put an expiry on it — a reminder, a ticket, a timer — because temporary DEBUG has a way of becoming permanent.

One thing *not* to automate: lowering verbosity when the system is under load. It sounds sensible, but it means the moment the system starts struggling is the moment it stops telling you why. If logging volume threatens the service under load, fix the logging path (async, sampled, bounded), not the information.

## Choosing the Right Level Under Pressure

When an incident is active and you need more signal, the instinct is to turn everything up to DEBUG or TRACE. Resist it. Verbose logging under load adds CPU and I/O pressure to a system that's already struggling, and the extra volume makes the relevant lines harder to find, not easier. Turn on DEBUG only for the component you're investigating.

When you're unsure which level an event deserves while writing code, ask what the reader should *do* about it. Act now: ERROR. Act soon: WARN. Nothing to do, but it explains what happened: INFO. Only useful while debugging: DEBUG. If in doubt, go less severe. An over-promoted ERROR does more damage, because it teaches people to ignore ERRORs, than a WARN that should have been an ERROR does by being read an hour later.

A practical level-to-impact mapping that reflects how on-call teams actually triage:
- **ERROR**: anything that directly affects what a user experienced
- **WARN**: anything that might, if left alone
- **INFO**: anything that helps reconstruct what a user experienced
- **DEBUG**: anything that helps explain why

## Sampling High-Frequency Events

For high-frequency INFO events, logging a sample keeps statistical coverage at a fraction of the volume. Record the rate on the line, so that anything counting these lines can scale the count back up:

```csharp
// 1.0 = always log; fractional = sample rate
private static readonly Dictionary<string, double> _sampleRates = new()
{
    ["payment.processed"] = 1.00,  // always: every payment matters
    ["order.placed"]      = 1.00,
    ["api.call"]          = 0.10,  // 10% sample
    ["cache.hit"]         = 0.01,  // 1% sample
    ["health.check"]      = 0.001, // 0.1% sample
};

public void LogSampled(ILogger logger, string eventName, string message, params object[] args)
{
    var rate = _sampleRates.GetValueOrDefault(eventName, 0.05);

    // Random.Shared is thread-safe; a shared new Random() is not
    if (Random.Shared.NextDouble() < rate)
    {
        using var scope = logger.BeginScope(
            new Dictionary<string, object> { ["event.name"] = eventName, ["sampling.rate"] = rate });
        logger.LogInformation(message, args);
    }
}
```

`sampling.rate` lets a pipeline extrapolate: N lines at rate 0.01 represent about 100N events. Without it, sampled logs look like complete counts and mislead every rate-of-change query built on them.

Random sampling per line has one weakness: the lines of a single request are sampled independently, so a request's story arrives with gaps. If your traces are already sampled, keeping all the logs of sampled traces and few of the rest gives you whole stories instead of fragments. [Your Sampling Strategy Is Lying to You](/articles/sampling-strategy/) covers the trade-offs.

## Circuit Breakers: Log the Transition, Not Every Failure

A circuit breaker sees every failure of the call it protects, which makes it tempting to log each one, at a level based on how bad things look. Don't log per failure. The exception already goes to the caller, and logging it in the breaker too is log-and-throw again. What the breaker knows that nobody else does is the *trend*. Log when that changes:

```csharp
private LogLevel _lastLevel = LogLevel.Information;

internal static LogLevel DetermineLogLevel(double errorRate, int consecutiveFailures) =>
    (errorRate, consecutiveFailures) switch
    {
        (> 0.5, _)   => LogLevel.Error,       // high error rate: the circuit should open
        (_, > 10)    => LogLevel.Error,       // long run of consecutive failures
        (> 0.1, > 3) => LogLevel.Warning,     // moderate degradation
        _            => LogLevel.Information  // isolated failures
    };

public void RecordOutcome(double errorRate, int consecutiveFailures)
{
    var level = DetermineLogLevel(errorRate, consecutiveFailures);
    if (level == _lastLevel) return;   // one line per change, not per failure

    _logger.Log(level,
        "{Operation} health changed {From} -> {To}: consecutive={ConsecutiveFailures} rate={ErrorRate:P1}",
        _operation, _lastLevel, level, consecutiveFailures, errorRate);
    _lastLevel = level;
}
```

A burst that goes from healthy to degraded to failing and back produces four lines (`Information → Warning`, `Warning → Error`, `Error → Information`) instead of thousands. The thresholds (0.5, 10, 0.1, 3) are a starting point. Calibrate them against your service's normal error rate and its SLO error budget. `DetermineLogLevel` is a pure function, so unit-test it directly with (errorRate, consecutiveFailures) pairs. The breaker itself is covered in [High-Throughput Logging: Keeping the Hot Path Fast](/guides/high-throughput-logging/#circuit-breakers).

## Quick Reference

| Level | `SeverityNumber` | Trigger | Operator action | Production default |
|-------|---|---------|-----------------|-------------------|
| FATAL | 21–24 | The process can't continue | Restart, then investigate | Always on |
| ERROR | 17–20 | Operation failed, user impact | Investigate now | Always on |
| WARN | 13–16 | Degraded or at risk, still working | Investigate soon | Always on |
| INFO | 9–12 | Significant event completed | Read during review | On, high-volume events sampled |
| DEBUG | 5–8 | Internal state for diagnosis | Turn on while investigating | Off |
| TRACE | 1–4 | Step-by-step execution | Dev or targeted sessions | Off |

---

**Next**: [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/) — the field names that go alongside the level.
