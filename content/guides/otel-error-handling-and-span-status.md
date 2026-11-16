---
title: "OTel Error Handling: What to Record, What to Set, and Why It Matters for Alerting"
date: 2026-11-16
draft: false
excerpt: "A thrown exception isn't always a failed span, and a caught one almost never is. Span status, exception recording, and error.type are separate decisions. Get them wrong and your error rate alerts are lying to you."
readtime: 8
tags: ["OpenTelemetry", "Tracing", "Observability", "Best Practices", "Alerting"]
card:
  title: "Span Status and Errors: What OTel Records for You"
---

Most teams instrument errors last. Traces work, spans show up in the UI, and everyone assumes errors will look after themselves. Some do. The ones you catch and handle don't, and those are usually the ones your users feel.

There are three decisions: what the span's status is, whether the exception gets recorded, and what counts as an error for your SLO. Your SDK makes some of them for you. You need to know which.

The Python behaviour below was run against `opentelemetry-sdk` **1.45.2**. The rules come from the OpenTelemetry specification **v1.62.0** and semantic conventions **v1.45.0**.

## Span status: the three states

Every span has a status with one of three values:

- **`UNSET`**, the default. Nobody said anything. Backends treat it as "not an error".
- **`ERROR`**: the operation failed. This is what error-rate metrics count.
- **`OK`**: someone explicitly declared success.

Leave successful spans at `UNSET`. You don't need to set `OK` on the happy path, and the spec asks instrumentation libraries not to. `OK` is a deliberate override, and it's final. Once a span is `OK`, a later `set_status(ERROR)` is ignored. Reach for it only when you want to say "I know what this looks like, and it's fine".

## What the SDK does for you, and what it doesn't

This is where most write-ups get it wrong, in both directions.

**An exception that escapes the span is handled for you in Python.** `start_as_current_span` records the exception and sets `ERROR` by default:

```python
with tracer.start_as_current_span("process-payment") as span:
    payment_service.charge(amount)   # raises PaymentDeclined
```

That span ends with status `ERROR`, the description `PaymentDeclined: card declined`, and one `exception` event. You wrote no error-handling code. The two parameters behind it are `record_exception=True` and `set_status_on_exception=True`, and you can turn either off.

**An exception you catch is invisible.** This is the trap:

```python
with tracer.start_as_current_span("process-payment") as span:
    try:
        payment_service.charge(amount)
    except PaymentDeclined:
        return fallback_response()
```

That span ends `UNSET`, with no events. The payment failed, the user saw a fallback, and your trace says everything went fine. If the failure matters, say so:

```python
with tracer.start_as_current_span("process-payment") as span:
    try:
        payment_service.charge(amount)
    except PaymentDeclined as e:
        span.set_status(StatusCode.ERROR, "card declined")
        span.set_attribute("error.type", type(e).__qualname__)
        return fallback_response()
```

**Don't do both by hand and then re-raise.** A common pattern calls `span.record_exception(e)` and `span.set_status(...)` inside the `except` block and then raises again. In Python the context manager then records the same exception a second time, and you get two identical `exception` events on one span. If you re-raise, let the SDK do the recording.

**This is Python's behaviour, not a law.** The automatic handling only exists when you use the context manager. A span you create with `start_span()` and end yourself gets nothing. Other languages differ: in Java and Go you record the error and set the status yourself. Check what your SDK does before you trust your error rate.

## record_exception, set_status, and error.type

Three calls, three different jobs:

**`span.set_status(StatusCode.ERROR)`** marks the span as failed. Error-rate metrics derived from spans count this. It adds no detail about what went wrong.

**`span.record_exception(e)`** attaches the exception's type, message, and stack trace. It doesn't change the status. A span with a recorded exception and no `ERROR` status still counts as a success.

**`error.type`** is a span attribute, and it's the one people forget. It's a short, low-cardinality label for the class of failure: an exception type, or a status code as a string. It's a stable convention, and it's what lets you break an error rate down by cause without parsing stack traces.

The status description is free text for a human. Keep sensitive data out of it. Exception messages have a habit of quoting the input that upset them.

### Exceptions are moving to logs

`record_exception` writes a span event. As of semantic conventions v1.45.0, recording exceptions as span events is deprecated, and the replacement is recording them as logs that carry the trace and span IDs. The API method still exists and still works. Instrumentation is meant to switch only when you opt in with `OTEL_SEMCONV_EXCEPTION_SIGNAL_OPT_IN`. Nothing breaks today, but don't build new dashboards on exception span events. [OTel Semantic Conventions](/guides/otel-semantic-conventions/) has the details.

## What counts as an error

Not every exception or non-200 is a failed span. For HTTP, the conventions give a rule, and it depends on which side of the call the span sits:

| Response | Server span | Client span |
|-------|-----------|--------|
| 5xx | `ERROR` | `ERROR` |
| 4xx (404, 401, 422, 429) | `UNSET` | `ERROR` |
| Connection failed, timed out | n/a | `ERROR` |

The logic: a server that returns 404 did its job. The caller asked for something that isn't there. From the client's side, the request it made failed. Both spans are right.

That 4xx rule is the default for instrumentation that knows nothing else. You know more. If your client asks "does this record exist?" and a 404 is a normal answer, you can decide that span isn't an error.

For your own business logic there's no table, so use one test: **did the operation do what its caller needed?**

- A declined card: the payment span failed, even though no system broke.
- A validation error you returned cleanly: not an error. You did your job.
- A retry that eventually succeeded: the attempts failed, the operation didn't.

This matters for your error budget. Mark every 404 as an error and your budget burns on typos and expired links. Mark nothing you catch and it never burns at all.

## Auto-instrumentation

Instrumentation libraries for HTTP frameworks and clients apply the table above for you. That's usually right. Two things to check:

- Some libraries, older versions especially, set `ERROR` on server spans for every 4xx. Look at a real 404 in your trace backend before you assume.
- Your error-rate query should be built on **server** spans or on the HTTP metrics. Count client spans as well and one failed call shows up twice.

## Structured error context

A stack trace tells you where. It doesn't tell you which decline code or which tenant. Put that in span attributes, where you can filter and group on it:

```python
span.set_attributes({
    "error.type": "payment_declined",
    "payment.decline_code": "insufficient_funds",
    "payment.currency": "USD",
})
```

Now "show me declined payments by decline code" is a query, not a grep. Keep the values bounded, and keep amounts and customer details out unless you've decided they belong in your traces.

## The checklist

Before you ship instrumented code:

- [ ] You know whether your SDK records escaping exceptions for you
- [ ] Every caught failure that matters sets `ERROR` and `error.type`
- [ ] Nothing records the same exception twice
- [ ] Successful spans are left `UNSET`, not set to `OK`
- [ ] Expected responses (404, 401, 422) aren't `ERROR` on server spans
- [ ] Status descriptions carry no sensitive data
- [ ] The error rate in your backend matches what you expect for the service

<!-- TODO: Add section on error propagation: when a child span errors, should the parent span also be set to ERROR? -->
<!-- TODO: Add Go, Java, Node.js examples -->
<!-- TODO: Add section on partial success: batch operations where some items fail -->
