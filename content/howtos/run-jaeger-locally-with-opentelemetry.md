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

## Running Jaeger with Docker Compose

1. Install Docker and Docker Compose if you haven't already.

2. Create a new directory for your Jaeger setup:
   ```bash
   mkdir jaeger-tracing
   cd jaeger-tracing
   ```

3. In this directory, create a file named `docker-compose.yml` with the following content:
   ```yaml
   version: "3"
   services:
     jaeger:
       image: jaegertracing/all-in-one:latest
       ports:
         - "16686:16686"  # Jaeger UI
         - "4317:4317"    # OTLP gRPC receiver
         - "4318:4318"    # OTLP HTTP receiver
   ```
   This file defines a single service, `jaeger`, which uses the `jaegertracing/all-in-one` image. This image bundles all Jaeger components into a single container for easy local testing.

4. In the same directory, run the following command:
   ```bash
   docker-compose up
   ```
   This command starts the Jaeger container defined in your `docker-compose.yml` file.

5. Open your browser and navigate to `http://localhost:16686`. You should see the Jaeger UI with a service dropdown and search panel.

## Configuring OpenTelemetry to Send Data to Jaeger

The OpenTelemetry Collector sits between your instrumented application and Jaeger. It receives spans over OTLP and forwards them to the backend — in this case, Jaeger, which has accepted OTLP directly since v1.35.

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
- An OTLP exporter targeting Jaeger's native OTLP endpoint at `jaeger:4317` — Jaeger has accepted OTLP directly since v1.35, so there is no need for the legacy `jaeger` exporter (removed in otelcol-contrib v0.86)
- A traces pipeline connecting the two

Save this configuration to a file named `collector-config.yaml`.

Now, update your `docker-compose.yml` file to include the Collector service:

```yaml
version: "3"
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
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

## What the Trace View Shows You

Navigate to `http://localhost:16686`. The UI is built around four views:

1. **Search**: Filter traces by service name, operation name, tags, duration range, and time window. Select a service from the "Service" dropdown and click "Find Traces" to get a list of matching traces.

2. **Trace Detail**: Clicking a trace opens the span waterfall — the full request path rendered as a timeline. Each row is one span: service name, operation name, start offset, and duration. Nested spans show parent-child relationships between services.

3. **Trace Statistics**: Aggregate counts of traces, services, and operations across the selected time range.

4. **Dependencies**: A service graph derived from span relationships in the stored traces, showing which services call which.

The Trace Detail view is where the work happens. You can see how long each operation took, where time was lost, and which service emitted an error tag — without grepping logs across five services.

## After the Setup

The Collector is the right place to extend this pipeline. Tail-sampling, attribute filtering, and routing all happen there — Jaeger stores whatever the Collector forwards. Once you have spans flowing locally, the next step is adding a sampling policy to the Collector so you're not storing every trace at full volume.
