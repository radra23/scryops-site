---
title: "Why are my structured logs still unstructured strings?"
date: 2026-10-01
draft: false
excerpt: "Three patterns that look like structured logging but aren't, in C#, Java, Go and Python, and what to write instead."
readtime: 4
tags: ["Logs", "Structured Logging", "Best Practices"]
---

**Q: I'm using a structured logging framework, but my log entries still arrive as plain text blobs. What's going wrong?**

Almost always one of three patterns. Each one looks fine in a code review, and each one hands your logger a finished sentence instead of fields. Pick your language below; the answer follows you down the page. Every snippet was run, and the comments show what actually came out.

---

### 1. Building the message yourself

{{< langswitch >}}
```csharp
// ❌ Concatenation or interpolation: the logger only ever sees the finished string
_logger.LogInformation("Processing order for user " + userId);
_logger.LogInformation($"Order {orderId} processed with amount {amount}");

// ✅ A message template: the braces name a field, the trailing arguments fill it
_logger.LogInformation("Order {OrderId} processed with amount {Amount}", orderId, amount);
// → Message "Order ord-9f2a processed with amount 142.5", fields OrderId, Amount
```
```java
// ❌ Concatenation or String.format: one opaque message
log.info("Processing order for user " + userId);
log.info(String.format("Order %s processed with amount %s", orderId, amount));

// ✅ SLF4J 2 key-value pairs: named fields next to a constant message
log.atInfo()
   .addKeyValue("order.id", orderId)
   .addKeyValue("order.amount", amount)
   .log("Order processed");
// Logback JsonEncoder → "kvpList": [{"order.id":"ord-9f2a"},{"order.amount":"142.5"}]
```
```go
// ❌ Concatenation or fmt.Sprintf: slog gets a msg and nothing else
slog.Info("processing order for user " + userID)
slog.Info(fmt.Sprintf("order %s processed with amount %.2f", orderID, amount))

// ✅ Key-value pairs after a constant message
slog.Info("order processed", "order.id", orderID, "order.amount", amount)
// → {"msg":"order processed","order.id":"ord-9f2a","order.amount":142.5}
```
```python
# ❌ f-string or concatenation: one opaque message
logger.info(f"Order {order_id} processed with amount {amount}")

# ✅ Fields in extra= (stdlib), or keyword arguments with structlog
logger.info("Order processed", extra={"order.id": order_id, "order.amount": amount})
log.info("order.processed", order_id=order_id, amount=amount)   # structlog
# OTel logging handler → attributes {"order.id": "ord-9f2a", "order.amount": 142.5}
```
{{< /langswitch >}}

The message arrives at the sink as a single string. There is no order ID to filter on and no amount to compare. The string is also built even when the level is filtered out, so you pay for it on every call.

The C# interpolated version is the one that fools reviewers, because `$"Order {orderId}"` looks exactly like a template. It isn't one: the interpolation runs before the logger is called. It also formats with the current culture. On a machine with a European locale, that test line came out as `amount 142,5` while the template version logged `142.5`. The analyzer rule CA2254 catches both forms, but it's not on by default. Turn it on with `<AnalysisLevel>latest-recommended</AnalysisLevel>` in the project file, or `dotnet_diagnostic.CA2254.severity = warning` in `.editorconfig`.

---

### 2. Placeholders that look like fields but aren't

Some placeholder syntaxes defer the formatting without creating any fields. They're better than building the string, but they don't give you structure.

{{< langswitch >}}
```csharp
// In C#, a template placeholder IS a field — this is the pattern to use.
_logger.LogInformation("Order {OrderId} processed", orderId);
// The name inside the braces becomes the field name, so keep it stable across calls:
// "{OrderId}" here and "{orderId}" elsewhere are two different fields.
```
```java
// ⚠️ SLF4J {} placeholders defer formatting, but they have no names
log.info("Order {} processed with amount {}", orderId, amount);
// Logback JsonEncoder → "arguments": ["ord-9f2a","142.5"] — positional, unnamed
// Use addKeyValue (above) when you need to query by field.
```
```go
// ⚠️ A value without a key: slog pairs it with a made-up key
slog.Info("order processed", orderID)
// → {"msg":"order processed","!BADKEY":"ord-9f2a"}
// go vet catches it: "call to slog.Logger.Info missing a final value"
```
```python
# ⚠️ %-style arguments defer formatting, but they aren't fields
logger.info("Order %s processed with amount %s", order_id, amount)
# OTel logging handler → body "Order ord-9f2a processed with amount 142.5", attributes {}
# Only extra= (or structlog keyword arguments) becomes a field.
```
{{< /langswitch >}}

---

### 3. Serializing objects into the message

{{< langswitch >}}
```csharp
// ❌ A JSON string inside the message: the structure is trapped in text
_logger.LogInformation("Order: " + JsonSerializer.Serialize(order));

// ⚠️ {@Order} destructures only under Serilog. With the built-in JSON console or the
// OpenTelemetry provider it becomes one string field literally named "@Order":
_logger.LogInformation("Order processed {@Order}", order);
// MEL / OTel → "@Order": "Order { Id = ord-9f2a, Amount = 142,5, Status = paid }"
// Serilog     → "Order": {"Id":"ord-9f2a","Amount":142.5,"Status":"paid"}

// ✅ Works with every provider: name the fields you need
_logger.LogInformation("Order {OrderId} processed: amount {Amount}, status {Status}",
    order.Id, order.Amount, order.Status);
```
```java
// ❌ toString() or a JSON string in the message
log.info("Order: " + order);
// → "message":"Order: Order[id=ord-9f2a, amount=142.5, status=paid]"

// ✅ Name the fields you need
log.atInfo()
   .addKeyValue("order.id", order.id())
   .addKeyValue("order.amount", order.amount())
   .addKeyValue("order.status", order.status())
   .log("Order processed");
```
```go
// ❌ A JSON string in the message
b, _ := json.Marshal(order)
slog.Info("order: " + string(b))

// ⚠️ slog.Any with a struct nests in the JSON handler, but the OpenTelemetry
// bridge (otelslog) flattens it to one string: "{ID:ord-9f2a Amount:142.5 Status:paid}"
slog.Info("order processed", "order", order)

// ✅ A group survives both handlers as real nested fields
slog.Info("order processed", slog.Group("order",
	"id", order.ID, "amount", order.Amount, "status", order.Status))
```
```python
# ❌ A JSON string in the message
logger.info("Order: " + json.dumps(order))

# ✅ Flat, named fields
logger.info("Order processed", extra={
    "order.id": order["id"], "order.amount": order["amount"], "order.status": order["status"],
})
```
{{< /langswitch >}}

Serializing the object yourself embeds JSON inside a string. Your log backend sees one field, `message = "Order: {\"id\":\"ord-9f2a\",…}"`. You can't filter on the amount or group by status; the structure is invisible to everything downstream.

The destructuring shortcuts are the trap here. They work with one library and quietly degrade with another, so the same line is structured in development and a string in production. Naming the fields explicitly works everywhere. It also documents what you meant to log, and stops a new property on the object, such as a customer's email, from leaking into your logs the day someone adds it. See [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) for how often that happens.

---

### Why the distinction matters at query time

The difference shows up when something breaks. With the value baked into the message, all you can do is match text:

```
message contains "payment failed" AND message contains "ord-9f2a"
```

That finds the lines that mention the order, but also any other line that happens to contain the string. And it can't answer questions about values. With fields, you can:

```
event.name = "payment.failed" AND order.id = "ord-9f2a"
event.name = "payment.failed" AND order.amount > 500
count by payment.provider where event.name = "payment.failed"
```

The second and third queries are impossible against a sentence. Numeric comparison and grouping need the value to exist as a value. On most backends field filters are also much cheaper than text matching, because they can use an index or labels instead of reading every line.

For the field names to use, see [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/). For where these lines fit in the bigger picture, see [Logging Foundations](/guides/logging-foundations/). And for one more anti-pattern that turns up in the same code reviews, log-and-throw, see [Log Levels](/guides/log-levels-and-severity/#1-log-and-throw).
