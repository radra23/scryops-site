---
title: "How to Instrument a Service with OpenTelemetry"
date: 2026-05-26
draft: false
excerpt: "From zero to traces, metrics, and correlated logs — in .NET, Go, or Python — using the stable OTel SDKs and a local Collector."
readtime: 9
tags: ["OpenTelemetry", "Python", "Tracing", "How-to"]
---

> "The first trace you capture from a service is the moment it stops being a black box."
> — A Backend Developer, Post-First Production Outage

Before instrumentation, your service is a sealed room. Requests go in, responses come out, and everything that happens in between is inference and guesswork. After instrumentation, every request leaves a trail: which path it took, how long each step took, and exactly where it went wrong.

The steps below are the same in every language — give the service an identity, let the framework instrument itself, name the work that matters, and connect logs to traces. The code differs; the shape doesn't. Each step shows the equivalent in **.NET**, **Go**, and **Python** — pick your tab.

{{< mermaid >}}
flowchart LR
    subgraph app["Your Service"]
        fw["Web framework<br/>(auto-instrumented)"]
        biz["Business logic<br/>(manual spans)"]
        log["Logger<br/>(trace_id injected)"]
    end
    sdk["OTel SDK<br/>Batch processor"]
    col["OTel Collector"]
    be1["Traces<br/>(Tempo / Jaeger)"]
    be2["Metrics<br/>(Mimir / Prometheus)"]
    be3["Logs<br/>(Loki / OpenSearch)"]

    fw --> sdk
    biz --> sdk
    log --> sdk
    sdk --> col
    col --> be1
    col --> be2
    col --> be3

    style sdk fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
    style col fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF
{{< /mermaid >}}

The instrumentation covers resource attributes, auto-instrumented HTTP and database spans, and log records that carry `trace_id` and `span_id` — all flowing through an OTel Collector to your backend of choice.

## What you'll need

- A runtime: **.NET 8/9**, **Go 1.23+**, or **Python 3.9+**
- An OTel Collector reachable at `localhost:4317` (or swap the endpoint for your backend's OTLP receiver)
- A web service to instrument — ASP.NET Core, Go `net/http`, or Flask/FastAPI. The patterns apply to any framework.

## Step 1 — Give Your Service an Identity

Every trace your service emits carries resource attributes that answer "where did this come from?" Before you can observe your service, it needs to know who it is — its `service.name`, `service.version`, and `deployment.environment`. Keep this setup in one place so you can swap backends without touching business code.

{{< codetabs >}}
```csharp
// dotnet add package OpenTelemetry.Extensions.Hosting OpenTelemetry.Exporter.OpenTelemetryProtocol
//                    OpenTelemetry.Instrumentation.AspNetCore OpenTelemetry.Instrumentation.Http
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r
        .AddService(serviceName: "checkout-api", serviceVersion: "1.4.0")
        .AddAttributes(new[]
        {
            new KeyValuePair<string, object>(
                "deployment.environment", builder.Environment.EnvironmentName),
        }))
    .WithTracing(tracing => tracing
        .AddOtlpExporter());     // gRPC http://localhost:4317 by default

var app = builder.Build();
```
```go
// go get go.opentelemetry.io/otel go.opentelemetry.io/otel/sdk \
//        go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc
package telemetry

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.40.0"
)

func InitTracer(ctx context.Context) (*sdktrace.TracerProvider, error) {
	exp, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint("localhost:4317"),
		otlptracegrpc.WithInsecure(), // plaintext for local; configure TLS in production
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.Merge(resource.Default(),
		resource.NewWithAttributes(semconv.SchemaURL,
			semconv.ServiceName("checkout-api"),
			semconv.ServiceVersion("1.4.0"),
			attribute.String("deployment.environment", "production"),
		))
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),   // batch — never SimpleSpanProcessor in production
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	return tp, nil // call tp.Shutdown(ctx) on shutdown to flush buffered spans
}
```
```python
# pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
# telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
import os

def init_tracing():
    resource = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "checkout-api"),
        "service.version": os.getenv("APP_VERSION", "1.4.0"),
        "deployment.environment": os.getenv("DEPLOY_ENV", "development"),
    })
    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
        insecure=True,  # set False and configure TLS in production
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))  # batch — not Simple in prod
    trace.set_tracer_provider(provider)
```
{{< /codetabs >}}

The resource attributes you define here appear on every span this service emits, forever — they're worth getting right. Two cross-language notes: in Python, `opentelemetry.sdk.resources` exports `SERVICE_NAME` but **not** `SERVICE_VERSION`, so use the string key `"service.version"` (as above). And the semantic convention for environment was renamed `deployment.environment.name` in recent semconv versions — most backends still index `deployment.environment`, so that's what the examples use; switch if your backend expects the newer key.

## Step 2 — The Work Your Framework Can Do for Free

OpenTelemetry's instrumentation libraries give you spans for every incoming request, every outbound HTTP call, and every database query — without touching a route handler.

{{< codetabs >}}
```csharp
// dotnet add package OpenTelemetry.Instrumentation.SqlClient
// Registered once at startup (extends the builder from Step 1):
builder.Services.AddOpenTelemetry().WithTracing(tracing => tracing
    .AddAspNetCoreInstrumentation()    // incoming HTTP requests
    .AddHttpClientInstrumentation()    // outgoing HttpClient calls
    .AddSqlClientInstrumentation()     // SQL queries
    .AddOtlpExporter());
```
```go
import (
	"net/http"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"github.com/XSAM/otelsql" // community-standard database/sql instrumentation
	"go.opentelemetry.io/otel/attribute"
)

// Inbound: wrap the handler — every request gets a span (method, route, status, duration).
handler := otelhttp.NewHandler(mux, "checkout-api")

// Outbound: wrap the client transport so spans continue into downstream services.
client := &http.Client{Transport: otelhttp.NewTransport(http.DefaultTransport)}

// Database/sql: open through otelsql for automatic query spans.
db, err := otelsql.Open("postgres", dsn,
	otelsql.WithAttributes(attribute.String("db.system", "postgresql")))
```
```python
# pip install opentelemetry-instrumentation-flask \
#             opentelemetry-instrumentation-requests \
#             opentelemetry-instrumentation-sqlalchemy
# app.py
from telemetry import init_tracing
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from flask import Flask

init_tracing()                          # must run before the instrumentors activate

FlaskInstrumentor().instrument()        # incoming HTTP requests
RequestsInstrumentor().instrument()     # outgoing requests calls
SQLAlchemyInstrumentor().instrument()   # SQL queries

app = Flask(__name__)
```
{{< /codetabs >}}

That handful of lines gives you spans for every HTTP request in, every outbound call, and every database query — named, timed, and tagged with status codes automatically. Your route handlers stay unchanged. (For FastAPI, swap the Flask instrumentor for `opentelemetry-instrumentation-fastapi`; in Go, wrap whichever router you use.)

## Step 3 — Name What Actually Matters

Auto-instrumentation covers the framework layer. But the work that matters to your business — processing a payment, validating an order, running a fraud check — happens inside those handlers, invisible to the framework instrumentor. That's where manual spans earn their keep.

{{< codetabs >}}
```csharp
using System.Diagnostics;

public static class Telemetry
{
    // One static ActivitySource per app/library; register it with .AddSource("Checkout.Payments").
    public static readonly ActivitySource Source = new("Checkout.Payments", "1.4.0");
}

public async Task<ChargeResult> ProcessPaymentAsync(string orderId, decimal amountUsd)
{
    using var activity = Telemetry.Source.StartActivity("payment.process");
    activity?.SetTag("order.id", orderId);
    activity?.SetTag("payment.amount_usd", amountUsd);
    activity?.SetTag("payment.provider", "stripe");
    try
    {
        var result = await _stripe.ChargeAsync(amountUsd);
        activity?.SetTag("payment.charge_id", result.Id);
        return result;
    }
    catch (Exception ex)
    {
        activity?.AddException(ex);                                // .NET 9+ (replaces RecordException)
        activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
        throw;
    }
}
```
```go
import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
)

var tracer = otel.Tracer("checkout/payments")

func ProcessPayment(ctx context.Context, orderID, provider string, amountUSD float64) error {
	ctx, span := tracer.Start(ctx, "payment.process")
	defer span.End()

	span.SetAttributes(
		attribute.String("order.id", orderID),
		attribute.Float64("payment.amount_usd", amountUSD),
		attribute.String("payment.provider", provider),
	)

	if err := charge(ctx, provider, amountUSD); err != nil {
		span.RecordError(err)                         // records the exception event
		span.SetStatus(codes.Error, "charge failed")  // RecordError does NOT set status itself
		return err
	}
	return nil
}
```
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def process_payment(order_id: str, amount: float) -> dict:
    with tracer.start_as_current_span("payment.process") as span:
        span.set_attribute("order.id", order_id)
        span.set_attribute("payment.amount_usd", amount)
        span.set_attribute("payment.provider", "stripe")
        try:
            result = stripe_client.charge(amount)
            span.set_attribute("payment.charge_id", result.id)
            return {"status": "ok", "charge_id": result.id}
        except StripeError as e:
            span.set_status(trace.StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise
```
{{< /codetabs >}}

Two conventions worth establishing from the start. Use dot-namespaced attribute names (`payment.amount_usd`, not `amount`), and always set an error **status**, not just an exception event — recording the exception and setting `Error` status are two separate calls in every SDK (in .NET, `AddException` replaced the now-obsolete `RecordException`; in Go, `RecordError` does not set status on its own). That `Error` status is what burn rate calculations downstream depend on — don't skip it.

## Step 4 — The Step Most Teams Skip

Here's where most teams stop short: connecting logs to traces. Right now your traces and logs are two separate islands. Add log/trace correlation and the manual timestamp search between them disappears.

{{< codetabs >}}
```csharp
builder.Logging.AddOpenTelemetry(logging =>
{
    logging.IncludeScopes = true;
    logging.AddOtlpExporter();          // logs exported with TraceId/SpanId attached
});
// ILogger calls inside a span now carry TraceId/SpanId automatically — no extraction.
```
```go
import "go.opentelemetry.io/contrib/bridges/otelslog"

// otelslog is pre-1.0 (beta) — pin the v0.x version deliberately.
slog.SetDefault(otelslog.NewLogger("checkout-api"))
// Log with slog.InfoContext(ctx, ...) so the active span's IDs are captured.
```
```python
# telemetry.py — add inside init_tracing()
import logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor

LoggingInstrumentor().instrument(set_logging_format=True)
logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] "
           "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s",
    level=logging.INFO,
)
```
{{< /codetabs >}}

Your observability platform can now jump from any span directly to the log lines from that exact request. The trade-offs between automatic injection and manual extraction — and how to verify correlation end to end — are covered in [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/).

## Step 5 — Confirm the Signal Is Flowing

Before pointing at your real backend, verify spans are arriving with a local Collector running the `debug` exporter:

```yaml
# collector-debug.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
```

```bash
# The debug exporter replaced the old `logging` exporter (removed in v0.111).
docker run --rm -p 4317:4317 -v "$PWD/collector-debug.yaml:/etc/otelcol/config.yaml" \
  otel/opentelemetry-collector-contrib
```

Make a request to your service. Spans should appear in the Collector logs within a few seconds, including resource attributes, span names, and any attributes you set manually.

If spans aren't arriving, there are two common culprits. First, confirm tracing was initialised before any requests were handled — the provider must be set before the instrumentors activate. Second, confirm the OTLP endpoint is reachable from your service's network context.

{{< insight lightbulb >}}
**Batch in production — this one matters.** A synchronous/simple span processor exports on every span end, blocking your request thread; under load it will quietly tank your latency. Use the batch processor in production (`WithBatcher` in Go, `BatchSpanProcessor` in Python; the .NET SDK batches by default). Reserve simple/synchronous export for local debugging when you need to see spans immediately.
{{< /insight >}}

## Your Service Now Emits Correlated Traces, Metrics, and Logs

Your service is no longer a black box. It's emitting:

- A root span for every incoming HTTP request, named by route, tagged with method and status code
- Child spans for every outbound HTTP call and database query, automatically
- Manual spans around your business logic with domain-specific attributes
- Log records with `trace_id` and `span_id` attached, ready for cross-signal correlation

From here, the natural next step is ensuring those trace IDs actually reach your log aggregator in a queryable form — covered in [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/). And once correlation works, the [Structured Logging guide](/guides/structured-logging-machine-readable/) shows you what schema to build on top of it.

Every request your service handles is now traceable end to end, with business context attached and log lines that follow the same trace ID.

{{< obs-mascot class="noob" tag="freshly leveled up, still hasn't finished the runbook" quip="BWOCK! Yesterday my service logged 'here', then 'here2', then a single 'WHY'. Today it emits traces, metrics, AND logs that carry a trace ID like they were raised right. I have read one (1) runbook. I have ASCENDED. Level 2, baby." caption="Bawkward shipped instrumentation and immediately took full credit for the entire observability stack." >}}
