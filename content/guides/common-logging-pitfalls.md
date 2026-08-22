---
title: "Common Logging Pitfalls and How to Avoid Them"
date: 2026-06-11
draft: true
excerpt: "The same logging mistakes appear across every team and technology stack: inconsistent field names, missing correlation context, PII in error logs, and high-frequency noise that buries real signals. Here is where to look and what to fix."
readtime: 9
tags: ["Logs", "Structured Logging", "Observability", "Best Practices"]
---

Logging mistakes are predictable. The same patterns appear across teams, stacks, and years — which means the fixes are also predictable. This guide covers the structural, content, and security pitfalls that most consistently degrade telemetry quality.

## Naming Inconsistency Across Services

The most common structural problem is using different field names for the same concept across services. When `user_id`, `userId`, `customerId`, and `sess_id` all mean the same thing in different services, cross-service queries become impossible without manual transformation.

```csharp
// ❌ Service A, B, C, D all log the same concept differently
_logger.LogInformation("{@Event}", new { userID = "123", sessionId = "abc" });    // Service A
_logger.LogInformation("{@Event}", new { user_id = "123", session_id = "abc" });  // Service B
_logger.LogInformation("{@Event}", new { customer_id = "123", sess_id = "abc" }); // Service D
```

```csharp
// ✅ Every service uses the same names
_logger.LogInformation("{@Event}", new
{
    user_id = "user_123",
    session_id = "session_abc",
    request_id = Activity.Current?.TraceId.ToString(),
    correlation_id = correlationId
});
```

Fix this at the standard level, not the code level: define a shared vocabulary of field names (ideally grounded in [OTel semantic conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)) and enforce it through log schema validation in CI. Naming problems that are allowed to compound across two years of log data can take months to normalize retroactively.

## Missing Correlation Context

A log entry with no trace ID, no correlation ID, and no service identifier is an island. It tells you something happened but provides no way to connect it to what triggered it, what happened before it, or what service emitted it.

```csharp
// ❌ No way to connect this to the request that caused it
_logger.LogInformation("User logged in", new { user_id = loginEvent.UserId });
```

```csharp
// ✅ Every log carries the context needed to link it to the trace
_logger.LogInformation("{@AuthEvent}", new
{
    timestamp = DateTimeOffset.UtcNow.ToString("O"),
    service = "authentication-api",
    service_version = "2.1.4",
    trace_id = Activity.Current?.TraceId.ToString(),
    span_id = Activity.Current?.SpanId.ToString(),
    event_type = "user_authentication",
    event_status = loginEvent.Success ? "success" : "failure",
    user_id = loginEvent.UserId,
    auth_method = loginEvent.AuthMethod
});
```

`Activity.Current` is the OTel .NET SDK's way of accessing the ambient trace context. If you are using `ActivitySource.StartActivity()` consistently, `Activity.Current` is populated automatically. You do not need to thread trace IDs through method signatures manually — attach them to the log at emission time.

## Data Type Inconsistency

Aggregation and filtering depend on consistent types. If `user_id` is an integer in one service and a string in another, you cannot write a query that joins them. If `amount` is a string in one place and a decimal in another, you cannot compute percentiles across services.

```csharp
// ❌ Same concepts, different types — these logs will not correlate
var serviceALog = new
{
    user_id = 12345,             // number
    order_amount = "99.99",      // string
    is_premium = "true",         // string boolean
    created_at = 1709736000L     // Unix epoch
};

var serviceBLog = new
{
    user_id = "user_12345",      // string with prefix
    order_amount = 99.99m,       // decimal
    is_premium = true,           // boolean
    created_at = "2024-03-06T12:00:00Z"  // ISO 8601
};
```

```csharp
// ✅ Consistent types, defined once in a shared convention
var standardLog = new
{
    user_id = $"user_{order.UserId}",           // always "user_<id>"
    order_amount = order.Amount,                 // always decimal
    is_premium = order.IsPremiumCustomer,        // always bool
    created_at = order.CreatedAt.ToString("O")   // always ISO 8601 UTC
};
```

Define type conventions in your shared logging schema: identifiers are strings with consistent prefixes, monetary values are decimals, timestamps are ISO 8601 UTC strings, counts are integers, booleans are booleans. Apply them at the point where domain objects are mapped to log fields — not in the log call itself.

## Embedding Values in Message Strings

Log entries where useful values are concatenated into the message string rather than emitted as separate fields cannot be filtered or aggregated on those values. This is the complement to the `.NET` anti-pattern of string interpolation in templates — it also applies to deliberately choosing to describe events in prose.

```csharp
// ❌ Processing time and error reason are inaccessible to queries
_logger.LogError(
    $"Payment attempt #{payment.AttemptNumber} for user {payment.UserId} " +
    $"failed after {payment.ProcessingTime}ms: {payment.ErrorReason}");
```

```csharp
// ✅ Every value is a queryable field
_logger.LogError("{@PaymentFailed}", new
{
    message = "Payment processing failed",
    user_id = payment.UserId,
    payment = new
    {
        id = payment.PaymentId,
        amount = payment.Amount,
        currency = payment.Currency,
        method = payment.PaymentMethod,
        attempt_number = payment.AttemptNumber
    },
    error = new
    {
        code = payment.ErrorCode,
        reason = payment.ErrorReason,
        is_retryable = payment.IsRetryable,
        processing_time_ms = payment.ProcessingTime.TotalMilliseconds
    }
});
```

The rule: if you would want to filter by a value, aggregate over it, or alert on it, it must be a field — not part of the message string.

## Over-Logging at High Frequency

Emitting a log entry for every iteration of a tight loop does not provide more information — it provides the same information N times, at a cost that scales with N.

```csharp
// ❌ 10,000 messages → 20,000 log entries, none more useful than two
foreach (var message in messages)
{
    _logger.LogDebug("Processing message {MessageId}", message.Id);
    await ProcessMessage(message);
    _logger.LogDebug("Message {MessageId} processed", message.Id);
}
```

```csharp
// ✅ One entry at start, one at completion, individual entries only for anomalies
public async Task ProcessMessageBatch(IEnumerable<Message> messages)
{
    var batch = messages.ToList();
    using var activity = ActivitySource.StartActivity("process_message_batch");
    activity?.SetTag("batch.size", batch.Count);

    var successCount = 0;
    var errorCount = 0;

    foreach (var message in batch)
    {
        try
        {
            var sw = Stopwatch.StartNew();
            await ProcessMessage(message);
            sw.Stop();
            successCount++;

            if (sw.ElapsedMilliseconds > SlowMessageThresholdMs)
            {
                _logger.LogWarning("{@SlowMessage}", new
                {
                    message = "Slow message processing",
                    message_id = message.Id,
                    message_type = message.Type,
                    processing_time_ms = sw.ElapsedMilliseconds
                });
            }
        }
        catch (Exception ex)
        {
            errorCount++;
            _logger.LogError(ex, "{@MessageFailed}", new
            {
                message = "Message processing failed",
                message_id = message.Id,
                message_type = message.Type
            });
        }
    }

    _logger.LogInformation("{@BatchCompleted}", new
    {
        message = "Message batch processing completed",
        total = batch.Count,
        succeeded = successCount,
        failed = errorCount,
        success_rate = (double)successCount / batch.Count
    });
}
```

Log individual events when they are anomalous — slow, failed, or unexpected. Log aggregate metrics for the normal case. The ratio of useful signal to volume should stay high regardless of throughput.

## PII and Sensitive Data in Logs

Logging personally identifiable information — email addresses, full names, addresses, phone numbers, social security numbers, payment card numbers — creates compliance liability under GDPR, PCI-DSS, and HIPAA, and turns your log aggregation system into a high-value data breach target.

```csharp
// ❌ A compliance incident waiting to be discovered
_logger.LogInformation("{@Registration}", new
{
    email = registration.Email,            // PII
    phone = registration.PhoneNumber,      // PII
    credit_card = registration.CardNumber, // PCI-DSS violation
    ssn = registration.SSN                 // Highly sensitive PII
});
```

```csharp
// ✅ Delete identifying values; log attributes, not values
_logger.LogInformation("{@Registration}", new
{
    user_id = registration.UserId,                    // internal ID, not derived from email
    age_band = GetAgeBand(registration.DateOfBirth),  // "25-34", not the date
    region = GetRegion(registration.Address),          // "EU-West", not the address
    account_type = registration.AccountType,
    acquisition_channel = registration.AcquisitionChannel,
    fraud_score = registration.FraudScore
});
```

The log should contain attributes that describe the user — tier, region, acquisition channel, risk score — not the values that identify them. The email itself is deleted, not hashed: the address space is small enough that a single GPU can walk the entire list of plausible addresses, so a hash isn't opaque the way it is for a high-entropy business identifier. Correlate on the internal `user_id` the account system already assigns — it does the same job without the email ever reaching the log.

Note that an internal user ID is still personal data under GDPR Article 4(5) once it can be tied back to an identity through the account record. If you need to support right-to-erasure (Article 17), a tokenisation registry with deletion capability is required — deleting the mapping from token to identity renders historical logs unlinkable. See [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) for when to hash, tokenise, or delete.

## Error Information Leaks

Exception details logged without filtering can expose internal system structure to anyone with log access — and log access is often broader than it should be.

```csharp
// ❌ Reveals database schema, server names, and code paths
catch (SqlException ex)
{
    _logger.LogError(ex, "Payment failed", new
    {
        connection_string = ex.DataSource,   // server hostname or IP
        procedure = ex.Procedure,            // database procedure name
        server = Environment.MachineName,    // infrastructure detail
        assembly = Assembly.GetEntryAssembly()?.Location  // deployment path
    });
}
```

```csharp
// ✅ Enough to diagnose; nothing an attacker needs
catch (Exception ex)
{
    _logger.LogError("{@PaymentError}", new
    {
        message = "Payment processing failed",
        error = new
        {
            category = CategoriseError(ex),   // "database_timeout", "network_error"
            type = ex.GetType().Name,          // "SqlException" — type is not sensitive
            code = GetErrorCode(ex),           // internal code like "ERR_PAY_DB_001"
            is_retryable = IsRetryable(ex)
        },
        operation = new
        {
            component = GetFailingComponent(ex), // "payment_gateway", "persistence"
            duration_ms = GetElapsedMs(),
            attempt = requestContext.AttemptNumber
        }
    });
}
```

Stack traces belong in structured exception telemetry (OTel exception events on the span), not in log entries that flow to shared aggregation. Infrastructure details — hostnames, file paths, connection strings — should never appear in logs.

## Log Size Inflation

Logging every HTTP header, full request bodies, or complete response payloads creates entries that are expensive to store, slow to index, and mostly noise.

```csharp
// ❌ Logs everything — headers alone can be several kilobytes
_logger.LogInformation("{@HttpRequest}", new
{
    headers = context.Request.Headers.ToDictionary(h => h.Key, h => h.Value),
    body = await ReadBodyAsync(context.Request),
    cookies = context.Request.Cookies.ToDictionary(c => c.Key, c => c.Value)
});
```

```csharp
// ✅ Logs what is useful; samples the rest
_logger.LogInformation("{@HttpRequest}", new
{
    method = context.Request.Method,
    path = context.Request.Path.Value,
    content_type = context.Request.ContentType,
    content_length = context.Request.ContentLength,
    // Selected headers only, not the full set
    correlation_id = context.Request.Headers["X-Correlation-ID"].ToString(),
    user_agent_category = CategoriseUserAgent(context.Request.Headers["User-Agent"]),
    // Body metadata, not body content
    body_size_bytes = context.Request.ContentLength ?? 0
});
```

Apply intelligent sampling for detailed captures: log full request context for error responses (`status >= 400`), requests that exceed a latency threshold, and a configured percentage of normal requests. Log metadata (size, type, category) for everything else.

<!-- TODO: Expand with Go and Python equivalents for naming/correlation patterns -->
<!-- TODO: Add section on log level misuse — DEBUG in production, WARN for expected conditions -->
<!-- TODO: Add section on timestamp pitfalls — local time instead of UTC, missing timezone info -->
