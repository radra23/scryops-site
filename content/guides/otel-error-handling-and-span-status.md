---
title: "OTel Error Handling: What to Record, What to Set, and Why It Matters for Alerting"
date: 2026-06-10
draft: true
excerpt: "An exception thrown does not automatically become a failed span. A failed span does not automatically become an error in your backend. The OTel error handling model requires explicit decisions — and getting them wrong means your error rate alerts are lying to you."
readtime: 8
tags: ["OpenTelemetry", "Tracing", "Observability", "Best Practices", "Alerting"]
---

Most teams instrument errors last. They get traces working, they see spans in the UI, and they assume errors will show up automatically. They usually do not — at least not correctly.

The OTel error model has three distinct steps: record the exception, set the span status, and decide what counts as an error in your SLO. Each step is explicit. Skipping any of them produces misleading data.

## Span Status: The Three States

Every span has a status with one of three values:

- **`UNSET`** (default): the span has not been explicitly marked as success or failure. Most spans start here.
- **`OK`**: the operation succeeded. Set this explicitly when you want to signal success.
- **`ERROR`**: the operation failed. This is what drives error rate metrics.

The critical point: **throwing an exception does not set span status to `ERROR` automatically**. You must set it.

```python
from opentelemetry.trace import StatusCode

with tracer.start_as_current_span("process-payment") as span:
    try:
        result = payment_service.charge(amount)
        span.set_status(StatusCode.OK)
    except PaymentDeclinedException as e:
        # Record the exception as a span event
        span.record_exception(e)
        # Set the span status to ERROR
        span.set_status(StatusCode.ERROR, description=str(e))
        raise
```

## record_exception vs set_status

These two calls do different things:

**`span.record_exception(e)`** adds a span event of type `exception` with the stack trace, exception type, and message. It is visible in the trace UI as an event on the timeline. It does **not** change the span status.

**`span.set_status(StatusCode.ERROR)`** marks the span as failed. This is what metrics exporters use to compute error rate. It does **not** automatically add the exception details.

You almost always want both. One without the other is incomplete:
- `record_exception` without `set_status(ERROR)` → the stack trace is visible but the span counts as success in error rate metrics
- `set_status(ERROR)` without `record_exception` → the span is counted as an error but there is no stack trace to debug

## What Counts as an Error

Not every exception should be an `ERROR` span. The rule: **set `ERROR` when the operation failed from the caller's perspective**.

Examples:
| Event | Set ERROR? | Reason |
|-------|-----------|--------|
| HTTP 500 from downstream | Yes | The operation failed |
| HTTP 404 (record not found) | No | The operation succeeded — the answer is "not found" |
| HTTP 429 (rate limited) | Depends | Error if you cannot retry; not if you have retry logic that succeeds |
| Validation error | No | The operation succeeded — the input was invalid, you returned a clear response |
| Database connection lost | Yes | The operation failed |
| User authentication failed | No | The operation succeeded — the credential was wrong |

The distinction matters for your SLO error budget. If you mark every 404 as an error, your error rate includes expected application behaviour and your error budget burns faster than user experience warrants.

## Auto-instrumentation and Errors

OTel auto-instrumentation libraries (for HTTP frameworks, database clients) set span status automatically based on the response. For HTTP:
- 5xx responses → `ERROR`
- 4xx responses → `UNSET` (not counted as errors in most implementations)

This is usually correct. Check your instrumentation library's behaviour before assuming — some older libraries set `ERROR` for all 4xx.

## Span Events for Structured Error Context

Beyond `record_exception`, you can add span events with custom attributes for structured error context:

```python
span.add_event(
    "payment.declined",
    attributes={
        "payment.decline_code": "insufficient_funds",
        "payment.amount": 99.99,
        "payment.currency": "USD",
    }
)
```

This is more queryable than a stack trace. Your backend can filter on `payment.decline_code = "insufficient_funds"` to understand the breakdown of payment failures.

## Operational Standards Checklist

Before shipping instrumented code:

- [ ] All exception paths call `record_exception` with the exception object
- [ ] All paths that represent true failures call `set_status(StatusCode.ERROR)`
- [ ] Expected non-success responses (404, 401, 422) are **not** marked ERROR
- [ ] Error descriptions are non-empty and human-readable
- [ ] Structured error context is added as span attributes or events, not just in the exception message
- [ ] Error rate in your backend matches your expectation for the service

<!-- TODO: Add section on error propagation — when a child span errors, should the parent span also be set to ERROR? -->
<!-- TODO: Add Go, Java, Node.js examples -->
<!-- TODO: Add section on partial success — batch operations where some items fail -->
