---
title: "How to Wire Trace IDs Into Your Logs"
date: 2026-05-26
draft: false
excerpt: "Logs and traces live in separate worlds until you connect them. Wire trace context into your log output — in .NET, Go, or Python — and let your observability platform handle correlation automatically."
readtime: 8
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

Two approaches cover the common cases in every language: let the SDK inject trace context automatically, or extract it from the active span yourself. Which one fits depends on a single question — do your logs already flow through the OpenTelemetry pipeline, or are they plain lines on stdout that an agent scrapes?

{{< mermaid >}}
flowchart TD
    A{Logs exported through<br/>the OTel pipeline / OTLP?} -->|yes| E[Automatic injection — start here]
    A -->|no — plain stdout / JSON| C{Need selective control<br/>or an unsupported logger?}
    C -->|no| E
    C -->|yes| D[Manual extraction]
    style E fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
{{< /mermaid >}}

## What you'll need

- A service that already creates spans — a `TracerProvider`/tracing pipeline initialised. Trace IDs in logs are only meaningful when there are traces to correlate them with.
- Your platform's standard logger: `ILogger` (.NET), `slog` (Go), or the `logging`/`structlog` stack (Python).

If your service isn't yet instrumented, start with [How to Instrument a Service with OpenTelemetry](/howtos/instrument-python-service-opentelemetry/) first.

## Approach 1 — Let the SDK Inject Trace Context

This is the right approach when your logs flow through the OpenTelemetry logging pipeline. The SDK reads the active span and stamps `trace_id` and `span_id` onto every record emitted inside it — no per-call work.

{{< codetabs >}}
```csharp
// Program.cs — logs emitted inside an Activity carry TraceId/SpanId automatically.
// OpenTelemetry.Extensions.Hosting + OpenTelemetry.Exporter.OpenTelemetryProtocol
builder.Logging.AddOpenTelemetry(logging =>
{
    logging.IncludeScopes = true;
    logging.IncludeFormattedMessage = true;
    logging.AddOtlpExporter();          // gRPC http://localhost:4317 by default
});

// Anywhere inside an active span — no manual extraction:
_logger.LogInformation("Charging order {OrderId}", order.Id);
// emitted record: TraceId=<32 hex>, SpanId=<16 hex>, matched to the active Activity
```
```go
// otelslog reads the active span off the context and attaches trace_id/span_id.
// go.opentelemetry.io/contrib/bridges/otelslog — pre-1.0 (beta); pin the v0.x version.
import (
	"context"
	"log/slog"

	"go.opentelemetry.io/contrib/bridges/otelslog"
)

func main() {
	slog.SetDefault(otelslog.NewLogger("payments")) // backed by the global LoggerProvider
}

func handle(ctx context.Context) {
	// MUST use the ...Context variant so the active span is read from ctx.
	slog.InfoContext(ctx, "charging order", "order.id", orderID)
}
```
```python
# LoggingInstrumentor stamps otelTraceID/otelSpanID onto stdlib logging records.
# pip install opentelemetry-instrumentation-logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor
import logging

logging.basicConfig(
    format=("%(asctime)s %(levelname)s [%(name)s] "
            "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s"),
    level=logging.INFO,
)
LoggingInstrumentor().instrument(set_logging_format=True)

# Every logger.info(...) during an active span now carries the IDs.
```
{{< /codetabs >}}

One distinction worth understanding, because it changes what "automatic" buys you. In .NET (`AddOpenTelemetry`) and Go (`otelslog`), your logs become OpenTelemetry log records *exported over OTLP* — correlation is built into the data model. Python's `LoggingInstrumentor` only *injects* the IDs into your existing stdlib records; it does not ship logs anywhere. To export Python logs through OTLP as well, add the Logs SDK's `LoggingHandler`. Either way, the correlation IDs are now present in the output.

When no span is active, the behaviours differ in a useful way: Python emits `otelTraceID` as `0000000000000000` (a clear signal the request wasn't traced), while the .NET and Go patterns simply omit the fields when there's no active span.

## Approach 2 — Extract Trace Context Yourself

Use this when your logs *don't* flow through OpenTelemetry — plain stdout or JSON scraped by an agent — or when you need selective control. Pull the IDs off the active span and attach them, guarding for the case where no span is active.

{{< codetabs >}}
```csharp
using System.Diagnostics;

// Read the IDs off the current Activity; attach them via a log scope.
public static void LogWithTrace(ILogger logger, string message)
{
    var a = Activity.Current;
    using (logger.BeginScope(new Dictionary<string, object>
    {
        ["trace_id"] = a?.TraceId.ToString() ?? "",   // 32 hex chars (W3C)
        ["span_id"]  = a?.SpanId.ToString()  ?? "",   // 16 hex chars (W3C)
    }))
    {
        logger.LogInformation("{Message}", message);
    }
}
```
```go
import (
	"context"
	"log/slog"

	"go.opentelemetry.io/otel/trace"
)

// traceHandler injects trace_id/span_id only when a valid span is on the context.
type traceHandler struct{ slog.Handler }

func (h traceHandler) Handle(ctx context.Context, r slog.Record) error {
	if sc := trace.SpanContextFromContext(ctx); sc.IsValid() {
		r.AddAttrs(
			slog.String("trace_id", sc.TraceID().String()), // 32 hex chars
			slog.String("span_id", sc.SpanID().String()),   // 16 hex chars
		)
	}
	return h.Handler.Handle(ctx, r)
}

// base := slog.NewJSONHandler(os.Stdout, nil)
// slog.SetDefault(slog.New(traceHandler{base}))
// slog.InfoContext(ctx, "payment completed")
```
```python
from opentelemetry import trace
import logging

logger = logging.getLogger(__name__)

def log_with_trace(message: str, level: str = "info", **kwargs):
    ctx = trace.get_current_span().get_span_context()
    extra = {}
    if ctx.is_valid:
        extra = {
            "trace_id": format(ctx.trace_id, "032x"),  # 32 hex chars
            "span_id": format(ctx.span_id, "016x"),    # 16 hex chars
        }
    getattr(logger, level)(message, extra={**extra, **kwargs})
```
{{< /codetabs >}}

The hex formatting is the part that silently bites people. `format(ctx.trace_id, "032x")` in Python, `.TraceID().String()` in Go, and `TraceId.ToString()` in .NET all produce the same thing: the 32-character (trace) and 16-character (span) lowercase-hex strings defined by the W3C Trace Context spec — the format Jaeger, Tempo, and every OTLP-compatible backend expect. Emit the raw integer or a truncated value and your log query will match nothing, even when the trace ID is technically correct.

### Structured loggers — enrich once

If you use a structured logging library, bind the trace context in one place rather than decorating every call. In Python with `structlog`, that's a processor:

```python
import structlog
from opentelemetry import trace

def add_otel_context(logger, method, event_dict):
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:                       # omit the field entirely outside a span
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

structlog.configure(processors=[
    add_otel_context,                      # inject trace context first
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.JSONRenderer(),
])
```

The same pattern applies elsewhere: a Serilog enricher reading `Activity.Current` in .NET, or the `slog.Handler` shown above in Go. Bind the IDs once and every event inherits them.

## Closing the Loop — Verify It's Working

After deploying, verification is two steps. Make a traced request, grab the trace ID from your backend, then search your log aggregator for that exact value.

A quick sanity check locally — if you're printing JSON logs to stdout:

```bash
curl http://localhost:8080/checkout
# In the output, look for:
# {"timestamp": "...", "level": "INFO", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", ...}
```

Take that `trace_id` and paste it into your tracing backend. You should see the corresponding trace. Paste the same value into your log aggregator. You should see exactly the log lines from that request — and only those lines.

❌ **If trace IDs appear as all zeros:**
Your logging setup is running before the `TracerProvider` is initialised. Move tracing initialisation earlier in your startup sequence, before any logging configuration runs.

✅ **If trace IDs are present but correlation isn't working in the UI:**
The field name may not match what your backend indexes. Most backends expect `trace_id` in snake_case. Datadog expects `dd.trace_id`. If there's a mismatch, add a field rename in the Collector's `transform` processor rather than changing your application code — it keeps the service portable.

{{< insight bookmark >}}
**The field name is a contract.** Your application, your Collector pipeline, and your observability backend all need to agree on what to call the trace ID field. Standardise on `trace_id` (32 hex chars) and `span_id` (16 hex chars) at the application level, and use the Collector to translate if any backend speaks a different dialect.
{{< /insight >}}

## Every Log Line Now Carries a Trace ID

{{< obs-trace-log-correlation >}}

Every log line emitted during a traced request now carries the trace ID. The path from alert to trace to log lines is a single click — the correlation that used to require manual timestamp searches now happens automatically.

Next: add business context to those log lines — `order.id`, `customer.tier`, `feature_flag` — so you can answer "who was affected?" from the log view without touching the database. That's the schema work in [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/).
