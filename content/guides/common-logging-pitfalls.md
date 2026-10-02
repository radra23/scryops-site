---
title: "Common Logging Pitfalls and How to Avoid Them"
date: 2026-06-11
draft: false
excerpt: "The same logging mistakes turn up in every team and every stack: inconsistent field names, values buried in message strings, missing trace context, personal data and secrets in error logs, and loops that log the same thing ten thousand times. Here is where to look and what to fix."
readtime: 9
tags: ["Logs", "Structured Logging", "Observability", "Best Practices"]
---

Logging mistakes are predictable. The same handful turn up across teams, stacks and years, which is good news: the fixes are predictable too. None of them is exotic. Each one quietly makes your logs harder to query, more expensive to keep, or more dangerous to leak.

The examples are C# with `Microsoft.Extensions.Logging`, because that's where many of these traps are easiest to show, but every pitfall here has a twin in Java, Go, Python and JavaScript. If you want the big picture first, start with [Logging Foundations](/guides/logging-foundations/).

## Every Service Names Things Its Own Way

The most common structural problem is one concept with five names. Service A logs `OrderId`, service B logs `order_id`, service C logs `orderNumber`. Each is fine on its own. Together they mean a cross-service query has to know every spelling, and nobody ever does.

```csharp
// ❌ Three services, one concept, three field names
_logger.LogInformation("Order {OrderId} placed", order.Id);       // checkout-api
_logger.LogInformation("Order {order_id} shipped", order.Id);     // fulfilment
_logger.LogInformation("Refund for {orderNumber}", order.Id);     // payments
```

Fix this at the standard level, not one call site at a time. Borrow names from [OpenTelemetry's semantic conventions](https://opentelemetry.io/docs/specs/semconv/) where they exist, invent your own in the same lowercase, dot-namespaced style where they don't, and write the list down. [Borrow Names Before You Invent Them](/guides/structured-logging-machine-readable/#borrow-names-before-you-invent-them) has a table of the ones that matter most.

Then make the standard hard to ignore. A shared package of source-generated log methods puts the names in one place, so a service can't misspell what it never types:

```csharp
// Shared package every service references: the names live here, once.
// [TagName] comes from Microsoft.Extensions.Telemetry.Abstractions.
public static partial class CheckoutLog
{
    [LoggerMessage(EventId = 1001, Level = LogLevel.Information,
        Message = "Order {order.id} placed by {customer.ref}")]
    public static partial void OrderPlaced(
        ILogger logger,
        [TagName("order.id")] string orderId,
        [TagName("customer.ref")] string customerRef);
}
```

Plain `[LoggerMessage]` won't accept a dotted placeholder like `{order.id}`. It needs a C# parameter of the same name, and the build fails with `SYSLIB1014`. `[TagName]` is what bridges the two. Naming drift across a whole fleet is covered in more depth in [Distributed Logging](/guides/distributed-logging/).

## Handing the Logger an Object and Hoping

A close cousin of the naming problem: logging an anonymous object with `{@Event}` and assuming every property becomes a field.

```csharp
// ❌ Looks structured. Isn't, unless Serilog is the provider.
_logger.LogInformation("{@Event}", new { order_id = "ord_12345", status = "placed" });
```

The `@` is Serilog's destructuring operator. With Serilog behind `ILogger` it does what you expect. With the built-in providers or the OpenTelemetry provider, the record gets **one** attribute, literally named `@Event`, holding the object's `ToString()`:

```
@Event: { order_id = ord_12345, status = placed }
```

That's a string that happens to look like data. You can't filter on `status` or group by `order_id`. If your provider isn't Serilog, name each field in the template instead.

## Values Buried in the Message String

The most familiar version of the same mistake is string interpolation:

```csharp
// ❌ One opaque string. Nothing in it is queryable.
_logger.LogError(
    $"Payment {payment.Id} attempt #{payment.AttemptNumber} failed after {elapsed.TotalMilliseconds}ms: {payment.ErrorType}");
```

```csharp
// ✅ Same sentence for humans, separate fields for machines
_logger.LogError(
    "Payment {payment.id} attempt {payment.attempt} failed after {duration_ms} ms: {error.type}",
    payment.Id, payment.AttemptNumber, elapsed.TotalMilliseconds, payment.ErrorType);
```

Run both through the OpenTelemetry provider and the difference is stark. The first produces a body and no attributes at all. The second produces the same readable message plus `payment.id`, `payment.attempt`, `duration_ms` and `error.type` as attributes, and a constant template that groups every occurrence of this event together. The interpolated version also builds its string even when the level is disabled.

A cheap guard rail: if you'd want to filter by a value, aggregate over it or alert on it, it has to be a field, not part of the sentence.

The opposite failure also happens. Pass arguments the template has no placeholder for, as in `_logger.LogInformation("User logged in", new { user_id = id })`, and they're silently dropped. The compiler only warns you (`CA2017`).

## Missing Trace Context

A log line with no trace ID is an island. It tells you something happened, but not which request caused it or what happened around it. The tempting fix is to copy `Activity.Current?.TraceId` into every log call by hand. Don't. It's repetitive, it's easy to forget, and it gives you yet another field name to keep consistent.

Let the logging pipeline attach it instead. `Activity` is .NET's own tracing type (`System.Diagnostics`), and OpenTelemetry .NET builds on it. With the OpenTelemetry logging provider, every record written inside an active span carries that span's `TraceId` and `SpanId` automatically:

```csharp
builder.Logging.AddOpenTelemetry(o =>
{
    o.IncludeFormattedMessage = true;
    o.AddOtlpExporter();   // OpenTelemetry.Exporter.OpenTelemetryProtocol
});
```

No change at any log call site. If you write JSON to stdout instead, set `ActivityTrackingOptions` and turn on `IncludeScopes`, and the JSON console formatter adds `TraceId` and `SpanId` to every line written inside a span. [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) walks through both routes for .NET, Java, Go and Python, including the Collector half that file-based logs need. Once the trace ID is there, [Log Context Enrichment](/guides/log-context-enrichment/) covers the next layer: the business and runtime context that makes a correlated line actually useful.

## Same Field, Different Types

Aggregation and filtering depend on types as much as names. If `order.amount` is a string in one service and a number in another, you can't sum it. If `customer.ref` is a number in one place and a prefixed string in another, the same customer looks like two.

```json
{ "order.amount": "99.99", "customer.premium": "true", "created_at": 1709726400 }
{ "order.amount": 99.99,   "customer.premium": true,   "created_at": "2024-03-06T12:00:00Z" }
```

Both lines describe the same kind of event, and no query will treat them as such. Put types in the shared convention next to the names:

- **Identifiers** are strings, with one consistent format per kind of ID.
- **Amounts** are numbers, with the currency in its own field rather than baked into the value.
- **Durations** are numbers, with the unit in the name (`duration_ms`).
- **Booleans** are booleans, never `"true"` or `"Y"`.
- **Timestamps** in your own fields are ISO 8601 with an explicit offset, ideally UTC.

The record's own timestamp is the SDK's job. OpenTelemetry stores it as nanoseconds since the Unix epoch, so it has no time zone to get wrong. The trouble starts with hand-rolled `created_at` fields in local time with no offset. Map domain objects to log fields in one place, not inside each log call, and type drift has nowhere to creep in. [Log-Based Monitoring](/guides/log-based-monitoring/#prerequisite-fields-you-can-count-on) shows what consistent fields buy you once you start alerting on them.

## Logging Every Iteration

Logging every item of a hot loop doesn't give you more information. It gives you the same information N times, at a cost that grows with N.

```csharp
// ❌ 10,000 messages → 20,000 lines, none more useful than the summary
foreach (var message in messages)
{
    _logger.LogInformation("Processing message {message.id}", message.Id);
    await ProcessMessage(message);
    _logger.LogInformation("Message {message.id} processed", message.Id);
}
```

Log the anomalies individually and the normal case as one summary:

```csharp
var failed = 0;
var sw = Stopwatch.StartNew();

foreach (var message in batch)
{
    var started = sw.ElapsedMilliseconds;
    try
    {
        await ProcessMessage(message);
        var elapsedMs = sw.ElapsedMilliseconds - started;
        if (elapsedMs > SlowMessageThresholdMs)
        {
            _logger.LogInformation("Slow message {message.id} ({message.type}) took {duration_ms} ms",
                message.Id, message.Type, elapsedMs);
        }
    }
    catch (Exception ex)
    {
        failed++;
        _logger.LogError(ex, "Message {message.id} ({message.type}) failed",
            message.Id, message.Type);
    }
}

_logger.LogInformation("Batch done: {batch.size} messages, {batch.failed} failed, in {duration_ms} ms",
    batch.Count, failed, sw.ElapsedMilliseconds);
```

A slow message is logged at INFO here, not WARN: nothing was lost and nothing needs doing yet. That follows the rule in [Log Levels](/guides/log-levels-and-severity/#choosing-the-right-level-under-pressure): when in doubt, go less severe. For events that are individually useful but too frequent to keep in full, [sample them and record the rate](/guides/log-levels-and-severity/#sampling-high-frequency-events). If the volume threatens the request path itself, that's a job for [Async Logging](/guides/async-logging/).

## The Wrong Level

Level misuse deserves its own page, and it has one. The two mistakes that do the most damage are worth repeating. ERROR for expected outcomes (a wrong password, a declined card) trains everyone to ignore ERROR. And paging on ERROR counts treats a log level as an incident severity, which [it isn't](/guides/log-levels-and-severity/#a-log-level-is-not-an-incident-severity). Use the [Log Levels](/guides/log-levels-and-severity/) guide as your team's reference and argue about it once.

## Personal Data in Logs

Emails, names, phone numbers, street addresses and card numbers in logs turn your log store into a breach target and a compliance problem. GDPR's data-minimisation principle covers telemetry like any other processing. PCI DSS requires card numbers to be unreadable wherever they're stored, and log stores count.

```csharp
// ❌ A compliance finding waiting to be discovered
_logger.LogInformation(
    "Registration {email} {phone} card {card_number}",
    registration.Email, registration.PhoneNumber, registration.CardNumber);
```

```csharp
// ✅ Attributes that describe the user, not values that identify them
_logger.LogInformation(
    "Registration {customer.ref} tier {customer.tier} region {customer.region} via {acquisition.channel}",
    customerRef, registration.Tier, registration.Region, registration.AcquisitionChannel);
```

Log what *describes* the user (tier, coarse region, acquisition channel) and a pseudonymous reference to correlate on, never the values that *identify* them. Don't make that reference a plain SHA-256 of the email address. Common addresses fall to precomputed tables, so the hash is barely better than the address. Use a keyed HMAC with the key held outside the telemetry system, or a token from a registry you control. [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/#a-decision-framework-for-every-field) has a field-by-field decision table.

A pseudonymous reference is still personal data under GDPR (Recital 26), because whoever holds the key or the token map can link it back. The upside is erasure: delete the mapping, and the historical logs can't be tied to the person any more. [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) covers when to hash, tokenise or delete. And because one developer will eventually log the wrong field anyway, put a scrubbing step in the Collector as a backstop. [The fix lives in the Collector](/guides/pii-in-telemetry/#the-fix-lives-in-the-collector-not-the-application), not only in application code.

## Secrets and Internals in Error Logs

Error paths are where secrets leak, because they're where developers reach for "log everything I can see."

```csharp
// ❌ Dumps whatever was in scope when it failed
catch (Exception ex)
{
    _logger.LogError(ex, "Payment failed. Connection: {db.connection_string} Request: {request.body}",
        _options.ConnectionString, requestBody);
}
```

A connection string can carry a password. A raw request body can carry a card number, an access token or the customer's address. Neither helps you diagnose a timeout.

```csharp
// ✅ Pass the exception; add the facts that classify the failure
catch (Exception ex)
{
    _logger.LogError(ex, "Payment {payment.id} failed: {error.type} (retryable: {error.retryable})",
        payment.Id, ClassifyError(ex), IsRetryable(ex));
}
```

Keep passing the exception itself. The OpenTelemetry provider carries it on the log record, and exporters write it out as the semantic-convention `exception.type`, `exception.message` and `exception.stacktrace` attributes. OpenTelemetry is moving exception recording [towards logs](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-logs/) rather than span events, so the log line is the right place for the stack trace. Infrastructure identity (`host.name`, `k8s.pod.name`, `service.version`) belongs on the record too, as resource attributes set once by the SDK or the Collector, not copied into each message.

Two cautions. Exception messages aren't sanitised: a database driver may echo the failing value, and the semantic conventions note that `exception.message` may contain sensitive data. Run the same Collector scrubbing over exceptions that you run over attributes. And control who can read the log store. Detailed errors are fine in logs; detailed errors readable by everyone are not.

## Logging Whole Requests

Logging every header, cookie and full body on every request creates lines that are expensive to store, slow to index and mostly noise. It's also a security problem, not just a size one: `Authorization` and `Cookie` headers are credentials.

If you're on ASP.NET Core, don't hand-roll it. The built-in HTTP logging middleware lets you choose the fields, and redacts the value of any header you haven't explicitly allowed:

```csharp
builder.Services.AddHttpLogging(o =>
{
    // Method, path, status and duration: no headers, no bodies.
    o.LoggingFields = HttpLoggingFields.RequestMethod
                    | HttpLoggingFields.RequestPath
                    | HttpLoggingFields.ResponseStatusCode
                    | HttpLoggingFields.Duration;
    o.CombineLogs = true; // one line per request, not one per phase
});

var app = builder.Build();
app.UseHttpLogging();
```

Its records are written under the `Microsoft.AspNetCore.HttpLogging.HttpLoggingMiddleware` category at Information, which the default templates filter out, so raise that category in `appsettings.json` or you'll see nothing. Watch the path, too: `/users/alice@example.com/orders` puts an email address in a field you thought was safe. If you already emit OpenTelemetry HTTP server spans, they carry method, route, status and duration, and a per-request log line may be redundant altogether.

When you need fuller detail, capture it for the requests that earn it, such as failed responses or a small fixed sample, and keep metadata (size, content type, status) for the rest.

{{< insight >}}
**The five-minute audit.**
Pick one service and pull an hour of its logs. Can you filter by every ID you'd need during an incident? Does every line carry a `trace_id`? Is there anything in there you'd be uncomfortable seeing in a breach report? Each "no" or "yes" maps to a section above, and fixing it in one service gives you the template for the rest.
{{< /insight >}}
