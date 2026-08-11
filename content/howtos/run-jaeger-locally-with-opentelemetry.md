---
title: "How to Run Jaeger Locally with OpenTelemetry"
date: 2026-06-07
draft: true
excerpt: "Set up a local Jaeger instance, configure the OTel Collector to forward traces, and use the Jaeger UI to explore distributed traces — all in Docker Compose."
readtime: 8
tags: ["Tracing", "Jaeger", "OpenTelemetry", "Collector", "How-to"]
---

## What is Jaeger?

A distributed trace records the path a single request takes across multiple services — each hop becomes a span, spans nest into a tree, and the tree becomes a trace. Without a trace backend, those spans are discarded the moment they're emitted. Jaeger is an open-source trace backend: it receives spans, stores them, and lets you query and visualize the full request path.

Running Jaeger locally gives you a trace store you control. You can instrument a service, send spans to the local instance, and inspect real trace data without touching a shared environment or signing up for anything.

{{< mermaid caption="Fig. — Spans travel over OTLP the whole way: from the instrumented service through the Collector to Jaeger's native receiver, then into the UI." >}}
flowchart LR
    app["Instrumented service<br/>(OTel SDK)"] -->|OTLP :4317| col["OTel Collector"]
    col -->|OTLP :4317| jaeger["Jaeger v2<br/>(receive + store)"]
    jaeger --> ui["Jaeger UI<br/>:16686"]
    style col fill:#1A1A2E,stroke:#3A6FAF,color:#5B8DEF,stroke-width:1.5px,stroke-dasharray:2 2
    style jaeger fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
{{< /mermaid >}}

## Running Jaeger with Docker Compose

1. Install Docker and Docker Compose if you haven't already.

2. Create a new directory for your Jaeger setup:
   ```bash
   mkdir jaeger-tracing
   cd jaeger-tracing
   ```

3. In this directory, create a file named `docker-compose.yml` with the following content:
   ```yaml
   services:
     jaeger:
       image: jaegertracing/jaeger:latest   # Jaeger v2 (all-in-one)
       ports:
         - "16686:16686"  # Jaeger UI
         - "4317:4317"    # OTLP gRPC receiver
         - "4318:4318"    # OTLP HTTP receiver
   ```
   This file defines a single service, `jaeger`, using the `jaegertracing/jaeger` image — Jaeger v2, which bundles every component into one container for local testing. (Jaeger v1's `jaegertracing/all-in-one` image reached end-of-life at the end of 2025.) Jaeger v2 accepts OTLP on ports 4317/4318 out of the box, so unlike v1 you don't need to set `COLLECTOR_OTLP_ENABLED`.

4. In the same directory, run the following command:
   ```bash
   docker-compose up
   ```
   This command starts the Jaeger container defined in your `docker-compose.yml` file.

5. Open your browser and navigate to `http://localhost:16686`. You should see the Jaeger UI with a service dropdown and search panel.

## Configuring OpenTelemetry to Send Data to Jaeger

In a real pipeline the OpenTelemetry Collector sits between your instrumented application and Jaeger. It receives spans over OTLP and forwards them to the backend — in this case, Jaeger, which has accepted OTLP directly since v1.35.

Collector configuration for this setup:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/jaeger]
```

This configuration defines:
- An OTLP receiver that accepts data over gRPC and HTTP
- An OTLP exporter targeting Jaeger's native OTLP endpoint at `jaeger:4317`. Because Jaeger speaks OTLP directly, there's no need for the standalone `jaeger` exporter — which was removed from the Collector in v0.86 (it last shipped in v0.85)
- A traces pipeline connecting the two

Save this configuration to a file named `collector-config.yaml`.

Now, update your `docker-compose.yml` file to include the Collector service:

```yaml
services:
  jaeger:
    image: jaegertracing/jaeger:latest
    ports:
      - "16686:16686"  # Jaeger UI

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: [ "--config=/etc/collector-config.yaml" ]
    volumes:
      - ./collector-config.yaml:/etc/collector-config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC — application traces go here
      - "4318:4318"   # OTLP HTTP — application traces go here
```

This adds a new service, `otel-collector`, which uses the `otel/opentelemetry-collector-contrib` image. It mounts the `collector-config.yaml` file we created earlier and exposes the OTLP receiver ports.

When you run `docker-compose up`, both Jaeger and the OpenTelemetry Collector will start. Your instrumented application can send data to the Collector at `http://localhost:4317` (gRPC) or `http://localhost:4318` (HTTP), and the Collector will forward it to Jaeger.

## Send a Test Trace

Before wiring up a whole service, confirm the pipeline works by emitting a single span to the Collector (or directly to Jaeger — both listen on `localhost:4317`). Each snippet below is a complete, minimal program.

{{< langswitch >}}
```csharp
// dotnet add package OpenTelemetry OpenTelemetry.Exporter.OpenTelemetryProtocol
using System.Diagnostics;
using OpenTelemetry;
using OpenTelemetry.Trace;

using var provider = Sdk.CreateTracerProviderBuilder()
    .AddSource("smoke-test")
    .AddOtlpExporter()                 // gRPC http://localhost:4317 by default
    .Build();

using var source = new ActivitySource("smoke-test");
using (source.StartActivity("hello-jaeger")) { }
// provider disposed here → flushes the span before exit
```
```go
// go get go.opentelemetry.io/otel go.opentelemetry.io/otel/sdk \
//        go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc
package main

import (
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func main() {
	ctx := context.Background()
	exp, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint("localhost:4317"), otlptracegrpc.WithInsecure())
	if err != nil {
		panic(err)
	}
	tp := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exp))
	otel.SetTracerProvider(tp)
	defer tp.Shutdown(ctx) // flush before exit

	_, span := otel.Tracer("smoke-test").Start(ctx, "hello-jaeger")
	span.End()
}
```
```python
# pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="localhost:4317", insecure=True)))
trace.set_tracer_provider(provider)

with trace.get_tracer("smoke-test").start_as_current_span("hello-jaeger"):
    pass
provider.shutdown()  # flush the span before exit
```
{{< /langswitch >}}

Run it, then refresh the Jaeger UI and pick `smoke-test` from the service dropdown — your `hello-jaeger` span should appear within a few seconds.

## What the Trace View Shows You

Navigate to `http://localhost:16686`. The UI is built around four views:

1. **Search**: Filter traces by service name, operation name, tags, duration range, and time window. Select a service from the "Service" dropdown and click "Find Traces" to get a list of matching traces.

2. **Trace Detail**: Clicking a trace opens the span waterfall — the full request path rendered as a timeline. Each row is one span: service name, operation name, start offset, and duration. Nested spans show parent-child relationships between services.

3. **Trace Statistics**: Aggregate counts of traces, services, and operations across the selected time range.

4. **Dependencies**: A service graph derived from span relationships in the stored traces, showing which services call which.

{{< obs-waterfall title="TRACE WATERFALL" total="240" critical="4"
      units="milliseconds · one request, GET /checkout · solid = self time, hatched = waiting on children"
      caption="Fig. — A trace is one request's story told in spans. The thin-bordered spans come free from auto-instrumentation; the thick-bordered payment.process span is the one you added by hand — but most of its bar is hatched, because it's waiting on the outbound Stripe call nested beneath it, which is the span that actually owns the latency. The dashed span is where it broke." >}}
[
  {"name":"GET /checkout","start":0,"duration":240,"self":20,"depth":0,"kind":"auto"},
  {"name":"auth.verify","start":8,"duration":16,"depth":1,"kind":"auto"},
  {"name":"SELECT cart_items","start":26,"duration":32,"depth":1,"kind":"auto"},
  {"name":"payment.process","start":62,"duration":152,"self":22,"depth":1,"kind":"manual"},
  {"name":"POST stripe.com/charge","start":70,"duration":130,"depth":2,"kind":"auto"},
  {"name":"UPDATE orders","start":216,"duration":20,"depth":1,"kind":"error"}
]
{{< /obs-waterfall >}}

The Trace Detail view is where the work happens. You can see how long each operation took, where time was lost, and which service emitted an error tag — without grepping logs across five services.

## After the Setup

The Collector is the right place to extend this pipeline. Tail-sampling, attribute filtering, and routing all happen there — Jaeger stores whatever the Collector forwards. Once you have spans flowing locally, the next step is adding a sampling policy to the Collector so you're not storing every trace at full volume.

{{< obs-mascot class="oracle" quip="I gaze into the span waterfall and I see ALL: the N+1 query, the retry storm, the 14-second call to a service that does nothing. Did I warn anyone? I am an Oracle, not a Slackbot. Open the trace. The prophecy is a flame graph." caption="Nostradamhen has foreseen every outage — confidently, in perfect detail, immediately after it happened." >}}
