---
title: "How to Instrument a Python Service with OpenTelemetry"
date: 2026-05-26
draft: true
excerpt: "From zero to traces, metrics, and correlated logs in a Python service — using the stable OTel SDK and a local Collector."
readtime: 8
tags: ["OpenTelemetry", "Python", "Tracing", "How-to"]
---

> "The first trace you capture from a service is the moment it stops being a black box."
> — A Backend Developer, Post-First Production Outage

Before instrumentation, your service is a sealed room. Requests go in, responses come out, and everything that happens in between is inference and guesswork. After instrumentation, every request leaves a trail: which path it took, how long each step took, and exactly where it went wrong.

{{< mermaid >}}
flowchart LR
    subgraph app["Your Python Service"]
        fw["Flask / FastAPI<br/>(auto-instrumented)"]
        biz["Business logic<br/>(manual spans)"]
        log["Logger<br/>(trace_id injected)"]
    end
    sdk["OTel SDK<br/>BatchSpanProcessor"]
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

- Python 3.9+
- An OTel Collector reachable at `localhost:4317` (or swap the endpoint for your backend's OTLP receiver)
- A Flask or FastAPI service to instrument — the patterns apply to any framework

## Step 1 — Gather Your Tools

Install the SDK and the instrumentation libraries for the frameworks your service uses:

```bash
pip install \
  opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-grpc \
  opentelemetry-instrumentation-flask \
  opentelemetry-instrumentation-requests \
  opentelemetry-instrumentation-sqlalchemy \
  opentelemetry-instrumentation-logging
```

For FastAPI, swap `opentelemetry-instrumentation-flask` for `opentelemetry-instrumentation-fastapi`. Everything else stays the same.

## Step 2 — Give Your Service an Identity

Every trace your service emits will carry resource attributes that answer the question "where did this come from?" Before you can observe your service, it needs to know who it is.

Create a dedicated `telemetry.py` module — keeping instrumentation setup out of your application logic makes it easy to swap backends without touching business code:

```python
# telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
import os

def init_tracing():
    resource = Resource.create({
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "my-service"),
        "service.version": os.getenv("APP_VERSION", "0.0.0"),
        "deployment.environment": os.getenv("DEPLOY_ENV", "development"),
    })

    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
        insecure=True,  # set False and configure TLS in production
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
```

Set `OTEL_SERVICE_NAME` and `APP_VERSION` via environment variable so the same container image works across environments without code changes. (`OTEL_SERVICE_VERSION` is not part of the OTel spec — the spec-compliant alternative is `OTEL_RESOURCE_ATTRIBUTES=service.version=1.2.3`, but injecting individual variables is simpler in most deploy pipelines.) The resource attributes you define here will appear on every span this service emits, forever — they're worth getting right.

## Step 3 — The Work Your Framework Can Do for Free

OpenTelemetry's instrumentation libraries give you spans for every incoming request, every outbound HTTP call, every database query — without touching a single route handler.

Call `init_tracing()` before your app initialises, then activate the instrumentors:

```python
# app.py
from telemetry import init_tracing
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from flask import Flask

init_tracing()

FlaskInstrumentor().instrument()
RequestsInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument()

app = Flask(__name__)
```

Those four lines give you spans for every HTTP request in, every `requests` call out, and every SQLAlchemy query — named, timed, and tagged with HTTP status codes automatically. Your route handlers stay unchanged.

## Step 4 — Name What Actually Matters

Auto-instrumentation covers the framework layer. But the work that matters to your business — processing a payment, validating an order, running a fraud check — happens inside those route handlers, invisible to the framework instrumentor. That's where manual spans earn their keep.

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
            span.set_attribute("payment.status", "success")
            span.set_attribute("payment.charge_id", result.id)
            return {"status": "ok", "charge_id": result.id}

        except StripeError as e:
            span.set_status(trace.StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise
```

Two conventions worth establishing from the start: use dot-namespaced attribute names (`payment.amount_usd`, not `amount`), and always record exceptions via `span.record_exception()` rather than just logging them. The `StatusCode.ERROR` status is what burn rate calculations downstream depend on — don't skip it.

## Step 5 — The Step Most Teams Skip

Here's where most teams stop short: connecting logs to traces.

Right now your traces and your logs are two separate islands. You can look at one or the other, but getting from a failed span to the log lines that explain *why* it failed requires a manual timestamp-based search. Add the OTel logging instrumentor and that search disappears:

```python
# telemetry.py — add inside init_tracing()
import logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor

def init_tracing():
    # ... existing TracerProvider setup ...

    # Inject trace_id and span_id into every log record automatically
    LoggingInstrumentor().instrument(set_logging_format=True)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(name)s] "
               "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s",
        level=logging.INFO,
    )
```

After this, every `logger.info(...)` call made while a span is active will automatically carry `otelTraceID` and `otelSpanID` in its log record. Your observability platform can now jump from any span directly to the log lines from that exact request.

## Step 6 — Confirm the Signal Is Flowing

Before pointing at your real backend, verify spans are arriving with a local Collector running the debug exporter:

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
otelcol --config collector-debug.yaml
```

Make a request to your service. Spans should appear in the Collector logs within a few seconds, including resource attributes, span names, and any attributes you set manually.

If spans aren't arriving, there are two common culprits. First, check that `init_tracing()` was called before any requests were handled — the `TracerProvider` must be set before the instrumentors activate. Second, confirm the OTLP endpoint is reachable from your service's network context.

{{< insight lightbulb >}}
**`BatchSpanProcessor` vs `SimpleSpanProcessor` — this one matters in production.** `SimpleSpanProcessor` exports synchronously on every span end, blocking your request thread. Under load, it will quietly tank your latency. Always use `BatchSpanProcessor` in production. Reserve `SimpleSpanProcessor` for local debugging when you need to see spans immediately, without buffering delay.
{{< /insight >}}

## Your Service Now Emits Correlated Traces, Metrics, and Logs

Your service is no longer a black box. It's emitting:

- A root span for every incoming HTTP request, named by route, tagged with method and status code
- Child spans for every outbound HTTP call and database query, automatically
- Manual spans around your business logic with domain-specific attributes
- Log records with `trace_id` and `span_id` attached, ready for cross-signal correlation

From here, the natural next step is ensuring those trace IDs actually reach your log aggregator in a queryable form — covered in [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/). And once you've got correlation working, the [Structured Logging guide](/guides/structured-logging-machine-readable/) shows you what schema to build on top of it.

Every request your service handles is now traceable end to end, with business context attached and log lines that follow the same trace ID.
