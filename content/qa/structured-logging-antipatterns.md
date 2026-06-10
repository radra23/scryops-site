---
title: "Why are my structured logs still unstructured strings?"
date: 2026-06-10
draft: false
excerpt: "Three C# patterns that look like structured logging but aren't — and what to do instead."
readtime: 3
tags: ["Logs", "Structured Logging", "Best Practices"]
---

**Q: I'm using a structured logging framework but my log entries still look like plain text blobs. What's going wrong?**

Three patterns cause this, and they all appear in code that is ostensibly using `ILogger` or Serilog correctly.

---

### Anti-pattern 1: String concatenation in the message

```csharp
// ❌ String concatenation — no structure, allocation on every call
_logger.LogInformation("Processing order for user " + userId);
```

The message arrives at the sink as a single opaque string. There is no `user_id` property to query. There is also no deferred evaluation — the string is allocated even if the log level is filtered out before writing.

```csharp
// ✅ Named template parameters — logged as typed properties
_logger.LogInformation("Processing order for user {UserId}", userId);
```

With named parameters, the logging framework stores `UserId = "user_abc"` as a separate structured property alongside the message template. It is queryable by name, type-correct, and only materialised into a string if the event actually gets written.

---

### Anti-pattern 2: String interpolation in the message template

```csharp
// ❌ Interpolated string — value is baked into the string before the logger sees it
_logger.LogInformation($"Order {orderId} processed with amount {amount}");
```

This looks like structured logging but is identical to anti-pattern 1 at runtime. By the time the string reaches the logger, the interpolation has already run — `orderId` and `amount` are embedded in the text, not passed as separate arguments. The framework has no values to capture as properties.

```csharp
// ✅ Template with positional arguments — preserves the values as properties
_logger.LogInformation("Order {OrderId} processed with amount {Amount}", orderId, amount);
```

The curly-brace syntax in `ILogger` and Serilog is *not* string interpolation. The braces name the property. The values are the trailing arguments. The framework handles the substitution — but it also captures each value as a structured field.

---

### Anti-pattern 3: Serializing objects into the message

```csharp
// ❌ Serialized JSON string — the structure is trapped inside a string blob
_logger.LogInformation("Order: " + JsonSerializer.Serialize(order));
```

This embeds a JSON string inside another string. Your log aggregator sees one field: `message = "Order: {\"id\":\"ord-9f2a\",\"amount\":142.5,...}"`. You cannot filter on `order.amount > 100`. You cannot aggregate by `order.status`. The structure is invisible to anything downstream.

```csharp
// ✅ Destructuring operator — emits the object's fields as structured properties
_logger.LogInformation("Order processed {@Order}", order);

// Or explicitly name the fields you need:
_logger.LogInformation(
    "Order {OrderId} processed: amount {Amount}, status {Status}",
    order.Id, order.Amount, order.Status);
```

The `@` prefix in Serilog (and the equivalent destructuring in other frameworks) tells the logger to decompose the object into its constituent properties. They appear as `Order.Id`, `Order.Amount`, `Order.Status` — individually queryable, individually indexable.

If you only need a few fields from a large object, the explicit form is preferable — it documents intent and avoids accidentally logging fields you did not mean to expose.

---

### Why the distinction matters at query time

The practical difference shows up when something breaks. With string concatenation or interpolation, your only query option is a substring match:

```
message contains "payment failed" AND message contains "ord-9f2a"
```

With structured properties, you can write:

```
event_type = "payment.failed" AND order.id = "ord-9f2a" AND order.amount > 500
```

The second query is O(log n) on an index. The first is O(n) full-text scan. At any serious log volume, the difference between the two is the difference between a sub-second query and one that times out.

<!-- TODO: Add Go and Python equivalents for the same anti-patterns -->
