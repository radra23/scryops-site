---
title: "How to Set Up Distributed Tracing with OpenTelemetry and Tempo"
date: 2026-03-18
draft: false
excerpt: "Instrument a microservice, ship spans to Grafana Tempo, and surface them in dashboards — zero proprietary vendor lock-in."
readtime: 6
tags: ["OpenTelemetry", "Tracing", "Grafana", "Tempo"]
---

This guide walks you through instrumenting a service with OpenTelemetry, shipping traces to Grafana Tempo, and querying them in Grafana — no vendor lock-in required.

## What you'll need

- A running service (we'll use a Go example)
- Docker or Kubernetes for running Tempo
- Grafana for visualization

## Step 1: Instrument your service

Install the OTel SDK:

```bash
go get go.opentelemetry.io/otel
go get go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc
go get go.opentelemetry.io/otel/sdk/trace
```

Initialize the tracer provider:

```go
package main

import (
    "context"
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func initTracer() (*sdktrace.TracerProvider, error) {
    exporter, err := otlptracegrpc.New(context.Background(),
        otlptracegrpc.WithEndpoint("localhost:4317"),
        otlptracegrpc.WithInsecure(),
    )
    if err != nil {
        return nil, err
    }

    tp := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(exporter),
    )
    otel.SetTracerProvider(tp)
    return tp, nil
}
```

## Step 2: Run the OTel Collector

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```

## Step 3: Deploy Tempo

```yaml
# tempo-config.yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:

storage:
  trace:
    backend: local
    local:
      path: /var/tempo/traces
```

## Step 4: Configure Grafana

Add Tempo as a data source in Grafana:

1. Go to **Configuration > Data Sources > Add data source**
2. Select **Tempo**
3. Set the URL to `http://tempo:3200`
4. Enable **TraceQL** for advanced querying

Now you can search for traces by service name, duration, or any span attribute using TraceQL:

```
{ resource.service.name = "my-service" && duration > 500ms }
```

## Next steps

- Add **span attributes** for business context (user ID, request type).
- Configure **tail sampling** in the collector to reduce storage costs.
- Set up **trace-to-logs** links in Grafana to correlate with Loki.
