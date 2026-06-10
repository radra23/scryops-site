---
title: "How to Wire Trace IDs Into Your Logs"
date: 2026-05-26
draft: false
excerpt: "Logs and traces live in separate worlds until you connect them. Wire trace context into your log output and let your observability platform handle correlation automatically."
readtime: 6
tags: ["OpenTelemetry", "Logs", "Tracing", "Python", "How-to"]
---

{{< obs-mascot class="ranger" tag="a developer, 4 hours into log-grepping" quip="A log line without a trace ID is a quest with no clues. You will still find the treasure — the hard way. FOUR HOURS of the hard way." caption="Bawkeye tracks the root cause by following the trail. Strip the trace IDs out of the logs and there is no trail — just four hours of searching the whole map by hand." >}}

When a burn rate alert fires, the ideal path from alert to root cause looks like this: alert → trace → the log lines that explain why. That last jump — from a span to the log lines emitted during that span — only works if your logs carry the trace ID. Without it, you're doing a time-based search across the logs of multiple services — no guarantee you'll find the relevant lines, and no way to limit the search to a single request.

{{< mermaid >}}
flowchart LR
    subgraph With["With trace IDs in logs"]
        A1[Alert fires] --> B1[Open trace]
        B1 -->|click| C1[Correlated log lines]
        C1 --> D1[Root cause]
    end
    subgraph Without["Without trace IDs in logs"]
        A2[Alert fires] --> B2[Open trace]
        B2 --> C2[Note timestamp]
        C2 --> D2[Search logs by time<br/>across all services]
        D2 --> E2[Filter manually]
        E2 --> F2[Maybe root cause]
    end
{{< /mermaid >}}

Three approaches cover the common cases: automatic SDK injection, manual span context extraction, and a structlog processor. Pick the one that fits your service's logging stack.

{{< mermaid >}}
flowchart TD
    A{Already using structlog?} -->|yes| B[structlog processor]
    A -->|no| C{Need selective injection<br/>or unsupported logger?}
    C -->|yes| D[manual extraction]
    C -->|no| E[automatic SDK — start here]
    style E fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
{{< /mermaid >}}

## What you'll need

- `opentelemetry-sdk` installed and a `TracerProvider` initialised — your service must already be creating spans
- Python's standard `logging` module, or `structlog`

If your service isn't yet instrumented, start with [How to Instrument a Python Service with OpenTelemetry](/howtos/instrument-python-service-opentelemetry/) first. Trace IDs in logs are only meaningful when there are traces to correlate them with.

## The Automatic Way — Let the SDK Do It

This is the right approach for most services. One call to the OTel logging instrumentor and every log record emitted during an active span will automatically carry `trace_id` and `span_id`.

```bash
pip install opentelemetry-instrumentation-logging
```

```python
from opentelemetry.instrumentation.logging import LoggingInstrumentor
import logging

# Call this after your TracerProvider is initialised
LoggingInstrumentor().instrument(set_logging_format=True)

logging.basicConfig(
    format=(
        "%(asctime)s %(levelname)s [%(name)s] "
        "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] "
        "%(message)s"
    ),
    level=logging.INFO,
)
```

Every `logger.info(...)`, `logger.error(...)`, or `logger.warning(...)` call made while a span is active will now include `otelTraceID` and `otelSpanID` in the log record. When no span is active, both fields emit as `0000000000000000` — a useful signal that the request wasn't traced.

For JSON log output, serialise the record fields rather than the format string:

```python
import json
import logging

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "otelTraceID", ""),
            "span_id": getattr(record, "otelSpanID", ""),
        })

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.getLogger().addHandler(handler)
```

## The Manual Way — When You Need Full Control

Use this when the instrumentor doesn't support your logging system, or when you need selective injection. Extract trace context directly from the active span:

```python
from opentelemetry import trace
import logging

logger = logging.getLogger(__name__)

def log_with_trace(message: str, level: str = "info", **kwargs):
    span = trace.get_current_span()
    ctx = span.get_span_context()

    extra = {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        **kwargs,
    }

    getattr(logger, level)(message, extra=extra)
```

Call it inside any traced context:

```python
with tracer.start_as_current_span("payment.process") as span:
    span.set_attribute("order.id", order_id)
    log_with_trace("Payment processing started", order_id=order_id, amount=amount)
    # ... do work ...
    log_with_trace("Payment completed", charge_id=result.id)
```

The `format(ctx.trace_id, "032x")` call converts the integer trace ID to the 32-character hex string defined by the W3C TraceContext spec — the format Jaeger, Tempo, and all OTLP-compatible backends expect. Get this format wrong and your log query will match nothing, even when the trace ID is right.

## The structlog Way — For Structured-First Codebases

If your service already uses `structlog`, add a processor that binds trace context to every log event automatically:

```python
import structlog
from opentelemetry import trace

def add_otel_context(logger, method, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

structlog.configure(
    processors=[
        add_otel_context,                          # inject trace context first
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
```

The `ctx.is_valid` guard omits `trace_id` entirely when no span is active — background jobs and health checks don't need a zero-value field cluttering the log.

## Closing the Loop — Verify It's Working

After deploying, the verification has two steps. Make a traced request, grab the trace ID from your backend, then search your log aggregator for that exact value.

A quick sanity check locally — if you're printing JSON logs to stdout:

```bash
curl http://localhost:8080/checkout
# In the output, look for:
# {"timestamp": "...", "level": "INFO", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", ...}
```

Take that `trace_id` and paste it into your tracing backend. You should see the corresponding trace. Paste the same value into your log aggregator. You should see exactly the log lines from that request — and only those lines.

❌ **If trace IDs appear as all zeros:**
Your logging setup is running before `init_tracing()` initialises the `TracerProvider`. Move `init_tracing()` earlier in your startup sequence, before any logging configuration runs.

✅ **If trace IDs are present but correlation isn't working in the UI:**
The field name may not match what your backend indexes. Most backends expect `trace_id` in snake_case. Datadog expects `dd.trace_id`. If there's a mismatch, add a field rename in the Collector's `transform` processor rather than changing your application code — it keeps the service portable.

{{< insight bookmark >}}
**The field name is a contract.** Your application, your Collector pipeline, and your observability backend all need to agree on what to call the trace ID field. Standardise on `trace_id` (32 hex chars) and `span_id` (16 hex chars) at the application level, and use the Collector to translate if any backend speaks a different dialect.
{{< /insight >}}

## Every Log Line Now Carries a Trace ID

{{< obs-trace-log-correlation >}}

Every log line emitted during a traced request now carries the trace ID. The path from alert to trace to log lines is a single click — the correlation that used to require manual timestamp searches now happens automatically.

Next: add business context to those log lines — `order.id`, `customer.tier`, `feature_flag` — so you can answer "who was affected?" from the log view without touching the database. That's the schema work in [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/).
