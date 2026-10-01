---
title: "How to Wire Trace IDs Into Your Logs"
date: 2026-10-01
draft: false
excerpt: "Logs and traces live in separate worlds until you connect them. Put the trace ID on every log line in .NET, Java, Go or Python, check where each runtime actually writes it, and make the field name a contract your backend can use."
readtime: 8
tags: ["OpenTelemetry", "Logs", "Tracing", "Python", "How-to"]
---

{{< obs-mascot class="ranger" tag="a developer, 4 hours into log-grepping" quip="A log line without a trace ID is a quest with no clues. You will still find the treasure — the hard way. FOUR HOURS of the hard way." caption="Bawkeye tracks the root cause by following the trail. Strip the trace IDs out of the logs and there is no trail — just four hours of searching the whole map by hand." >}}

When a burn rate alert fires, the ideal path from alert to root cause looks like this: alert → trace → the log lines that explain why. That last jump — from a span to the log lines emitted during that span — only works if your logs carry the trace ID. Without it, you're doing a time-based search across the logs of multiple services — no guarantee you'll find the relevant lines, and no way to limit the search to a single request.

{{< mermaid caption="Fig. — Trace IDs in logs turn root-causing from a manual timestamp search across every service into a single click from trace to log lines." >}}
flowchart TB
    subgraph With["With trace IDs in logs"]
        direction LR
        A1[Alert fires] --> B1[Open trace]
        B1 -->|click| C1[Correlated log lines]
        C1 --> D1[Root cause]
    end
    subgraph Without["Without trace IDs in logs"]
        direction LR
        A2[Alert fires] --> B2[Open trace]
        B2 --> C2[Note timestamp]
        C2 --> D2[Search logs by time<br/>across all services]
        D2 --> E2[Filter manually]
        E2 --> F2[Maybe root cause]
    end
    With ~~~ Without
{{< /mermaid >}}

Two approaches cover the common cases in every language: let the SDK or your logging library attach the trace context, or read it off the active span yourself. Start with the first. Reach for the second only when your logger has no integration, or you need the IDs under a specific field name the integration won't give you.

{{< mermaid caption="Fig. — Default to the integration your SDK or logger already ships; write the extraction yourself only when nothing attaches the IDs where your backend looks for them." >}}
flowchart LR
    A{Does your SDK or logger<br/>attach trace context?} -->|yes| E[Approach 1<br/>use the integration]
    A -->|no| D[Approach 2<br/>extract it yourself]
    E --> F{Do the IDs land where<br/>your backend looks?}
    F -->|yes| G[Done — verify it]
    F -->|no| H[Rename or parse<br/>in the Collector]
{{< /mermaid >}}

## What you'll need

- A service that already creates spans, with a tracing SDK initialised. Trace IDs in logs are only meaningful when there are traces to correlate them with. If you're not there yet, start with [How to Instrument a .NET Service](/howtos/instrument-dotnet-service-opentelemetry/) or [a Java Spring Boot Service](/howtos/instrument-java-service-opentelemetry/), or the [OpenTelemetry getting-started docs](https://opentelemetry.io/docs/languages/) for other languages.
- Your platform's standard logger: `ILogger` or Serilog (.NET), SLF4J with Logback (Java), `slog` (Go), or `logging`/`structlog` (Python).

Every snippet below was run against OpenTelemetry .NET 1.19.1, the Java agent 2.31.1, the Go `otelslog` bridge v0.20.1 and `opentelemetry-instrumentation-logging` 0.66b0 for Python.

## Approach 1 — Let the Integration Attach Trace Context

Each runtime has an integration that reads the active span and stamps its IDs onto every record emitted inside it, with no per-call work.

{{< langswitch >}}
```csharp
// Program.cs — OpenTelemetry.Extensions.Hosting + OpenTelemetry.Exporter.OpenTelemetryProtocol.
// Logs exported over OTLP carry TraceId/SpanId as first-class fields.
builder.Logging.AddOpenTelemetry(logging =>
{
    logging.IncludeFormattedMessage = true;
    logging.AddOtlpExporter();          // gRPC http://localhost:4317 by default
});

// Logging to stdout as JSON instead? The generic host already turns on
// ActivityTrackingOptions (TraceId | SpanId | ParentId); you only have to
// let scopes through to the output:
builder.Logging.AddJsonConsole(o => o.IncludeScopes = true);

// Anywhere inside an active span — no manual extraction:
_logger.LogInformation("Charging order {OrderId}", order.Id);
```
```java
// No code change. Start the JVM with the OpenTelemetry Java agent:
//   java -javaagent:opentelemetry-javaagent.jar -jar app.jar
// The agent puts trace_id, span_id and trace_flags into the SLF4J MDC
// (Logback and Log4j 2) for every log call made inside an active span.
// Reference them from your layout — logback.xml:
//
//   <pattern>%d %-5level %logger{20} trace_id=%X{trace_id} span_id=%X{span_id} - %msg%n</pattern>
//
// A JSON encoder that includes the MDC picks them up the same way.
log.info("charging order {}", order.getId());
```
```go
// otelslog sends slog records to the OpenTelemetry Logs SDK and reads the
// active span off the context.
// go.opentelemetry.io/contrib/bridges/otelslog — pre-1.0; pin the v0.x version.
import (
	"context"
	"log/slog"

	"go.opentelemetry.io/contrib/bridges/otelslog"
)

func main() {
	slog.SetDefault(otelslog.NewLogger("payments")) // backed by the global LoggerProvider
}

func handle(ctx context.Context) {
	// MUST use the ...Context variant: slog.Info has no ctx to read the span from.
	slog.InfoContext(ctx, "charging order", "order.id", orderID)
}
```
```python
# pip install opentelemetry-instrumentation-logging
# Adds otelTraceID / otelSpanID to every stdlib logging record.
import logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor

LoggingInstrumentor().instrument(inject_trace_context=True)
logging.basicConfig(
    format=("%(asctime)s %(levelname)s [%(name)s] "
            "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s"),
    level=logging.INFO,
)

# Every logger.info(...) during an active span now carries the IDs.
```
{{< /langswitch >}}

The Python flag matters. Older releases of the instrumentation added the fields on any `instrument()` call; current ones only do it with `inject_trace_context=True` (or `set_logging_format=True`, which also calls `basicConfig` with its own format). Leave it out and the format string above fails on every call with `Formatting field not found in record: 'otelTraceID'`.

"Automatic" means two different things here. With .NET's `AddOpenTelemetry` and Go's `otelslog`, your logs become OpenTelemetry log records shipped over OTLP, and the trace context is part of the record itself. The Java agent, the .NET JSON console and Python's instrumentation only *add the IDs to your existing output*. The text still goes wherever it went before, and your backend has to find the IDs in it. That is where the field name starts to matter.

### Where the IDs actually land

Run each integration and look at the output. The names are not the same:

| Integration | Field in the output | Outside a span |
|---|---|---|
| OTLP export (.NET, Go, Python, Java) | `TraceId` / `SpanId` fields of the log record | empty or all zeros |
| .NET JSON console | `TraceId` / `SpanId` inside the `Scopes` array | `Scopes` is empty |
| Serilog 3.1+ (compact JSON) | `@tr` / `@sp` | absent |
| Java agent + Logback | MDC `trace_id` / `span_id` / `trace_flags` | empty |
| Python instrumentation | `otelTraceID` / `otelSpanID` — named in your format | `0` |

Serilog needs no enricher at all: since 3.1 it captures the current `Activity`'s trace and span IDs on every event, and the compact JSON formatter writes them as `@tr` and `@sp`.

Only OTLP export gives the backend the IDs where OpenTelemetry defines them. For everything else, OpenTelemetry's [trace context in non-OTLP log formats](https://opentelemetry.io/docs/specs/otel/compatibility/logging_trace_context/) spec says what to aim for: top-level `trace_id`, `span_id` and `trace_flags`, lowercase hex. None of the stdout integrations above produce exactly that by default, so either configure your layout to use those names or translate them in the Collector (see [Closing the loop](#closing-the-loop--verify-its-working)).

## Approach 2 — Extract Trace Context Yourself

Use this when your logger has no integration, or you want the IDs under spec names in plain JSON on stdout. Read the IDs off the active span and attach them, skipping them when no span is active.

{{< langswitch >}}
```csharp
using System.Diagnostics;

// Read the IDs off the current Activity; attach them via a log scope.
public static void LogWithTrace(ILogger logger, string message)
{
    var a = Activity.Current;
    if (a is null) { logger.LogInformation("{Message}", message); return; }

    using (logger.BeginScope(new Dictionary<string, object>
    {
        ["trace_id"] = a.TraceId.ToString(),   // 32 hex chars (W3C)
        ["span_id"]  = a.SpanId.ToString(),    // 16 hex chars (W3C)
    }))
    {
        logger.LogInformation("{Message}", message);
    }
}
```
```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import org.slf4j.MDC;

// Without the agent: put the IDs in the MDC for the duration of the call.
SpanContext sc = Span.current().getSpanContext();
if (sc.isValid()) {
    try (MDC.MDCCloseable t = MDC.putCloseable("trace_id", sc.getTraceId());   // 32 hex chars
         MDC.MDCCloseable s = MDC.putCloseable("span_id", sc.getSpanId())) {   // 16 hex chars
        log.info("payment completed");
    }
}
```
```go
import (
	"context"
	"log/slog"

	"go.opentelemetry.io/otel/trace"
)

// traceHandler adds trace_id/span_id only when a valid span is on the context.
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

// Without these two, logger.With(...) returns the inner handler and the
// trace IDs silently disappear from every derived logger.
func (h traceHandler) WithAttrs(a []slog.Attr) slog.Handler { return traceHandler{h.Handler.WithAttrs(a)} }
func (h traceHandler) WithGroup(n string) slog.Handler      { return traceHandler{h.Handler.WithGroup(n)} }

// slog.SetDefault(slog.New(traceHandler{slog.NewJSONHandler(os.Stdout, nil)}))
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
    # The fields only reach the output if your formatter writes extras (a JSON formatter does).
    getattr(logger, level)(message, extra={**extra, **kwargs})
```
{{< /langswitch >}}

The Go wrapper is the one that bites quietly. Embedding `slog.Handler` makes `traceHandler` compile without `WithAttrs` and `WithGroup`. But the first `logger.With("order.id", id)` then hands back the plain JSON handler, and every line from that logger loses its trace ID with no error. Most real code logs through a derived logger, so the bug only shows up in production.

The hex formatting is the part that silently bites people in every language. `format(ctx.trace_id, "032x")` in Python, `.TraceID().String()` in Go, `getTraceId()` in Java and `TraceId.ToString()` in .NET all produce the same thing. That is a 32-character trace ID and a 16-character span ID in lowercase hex, as the W3C Trace Context spec defines them and as Jaeger, Tempo and every OTLP backend expect. Emit the raw integer or a truncated value and your log query matches nothing, even though the ID is technically correct.

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

The Go `slog.Handler` above is the same pattern; in .NET and Java the integrations already do it for you.

## Closing the Loop — Verify It's Working

Verification takes two steps. Make a traced request and grab its trace ID from your tracing backend. Then search your log aggregator for that exact value.

A quick sanity check locally, if you're printing JSON logs to stdout:

```bash
curl http://localhost:8080/checkout
# In the service's output, look for a line like:
# {"timestamp": "...", "level": "INFO", "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", ...}
```

Paste that `trace_id` into your tracing backend and you should see the trace. Paste the same value into your log aggregator and you should see the log lines from that request, and only those lines.

❌ **If the IDs are missing, `0`, or all zeros:**
The log call ran without an active span on its context. Common causes:
- It ran outside the span: before the request span started, or after it ended.
- In Go, it used `slog.Info` instead of `slog.InfoContext(ctx, …)`.
- The work hopped to another thread, goroutine or queue without carrying the context. [Context Propagation](/guides/otel-context-propagation/#where-propagation-breaks-inside-a-service) has a table of which hand-offs lose it in each runtime.
- No SDK `TracerProvider` was registered, so every span is a no-op with an invalid context.

❌ **If the IDs are present but the UI won't link logs to traces:**
The backend isn't reading them from where you wrote them. Over OTLP this doesn't happen. For text and JSON logs collected from files, have the Collector move the IDs into the log record's own trace fields as it parses the line. Then the service can keep writing whatever its integration emits:

```yaml
receivers:
  filelog:
    include: [/var/log/app/*.log]
    operators:
      - type: json_parser
        trace:
          trace_id:
            parse_from: attributes.trace_id   # e.g. attributes["@tr"] for Serilog
          span_id:
            parse_from: attributes.span_id
```

{{< insight bookmark >}}
**The field name is a contract.** Your application, your Collector pipeline and your observability backend all have to agree on where the trace ID lives. Prefer OTLP, where the record has a trace ID field and there is nothing to agree on. Otherwise write `trace_id` (32 hex chars) and `span_id` (16 hex chars) at the top level, as OpenTelemetry's non-OTLP spec says, and let the Collector translate for any backend that speaks a different dialect.
{{< /insight >}}

## Every Log Line Now Carries a Trace ID

{{< obs-trace-log-correlation >}}

Every log line emitted during a traced request now carries the trace ID. Going from alert to trace to log lines is a single click. The correlation that used to need a manual timestamp search now happens automatically.

Next, add business context to those log lines, such as an order ID, a customer tier or a feature flag, so you can answer "who was affected?" from the log view. [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/) covers the schema. [How to Enrich Logs with Business Context in .NET](/howtos/enrich-logs-with-business-context-dotnet/) walks through it in code. Keep [PII out of those fields](/guides/pii-in-telemetry/) while you're at it.
