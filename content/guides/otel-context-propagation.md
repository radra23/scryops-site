---
title: "Context Propagation: How Distributed Traces Stay Connected Across Services"
date: 2026-06-10
draft: true
excerpt: "A distributed trace is only as complete as its weakest propagation link. One service that drops the trace context header and the trace splits in two. A guide to W3C Trace Context, Baggage, and the propagation patterns that keep cross-service traces intact."
readtime: 9
tags: ["OpenTelemetry", "Tracing", "Observability", "Best Practices"]
---

A distributed trace is not stored in one place. It is assembled from spans emitted by dozens of services, each running independently. The only thing connecting them is a trace ID — a string passed from service to service in HTTP headers, message metadata, or gRPC context.

If that string stops being passed, the trace breaks. The spans still exist, but they are orphaned — disconnected from the request they were part of.

Context propagation is the mechanism that keeps the trace together.

{{< mermaid >}}
sequenceDiagram
    participant LB as Load Balancer
    participant A as Service A
    participant B as Service B
    participant C as Service C

    LB->>A: Request (no traceparent)
    Note over A: Creates root span<br/>trace-id: 4bf92f35...
    A->>B: Request + traceparent header
    Note over B: Creates child span<br/>same trace-id
    B->>C: Request + traceparent header
    Note over C: Creates child span<br/>same trace-id
    C-->>B: Response
    B-->>A: Response
    Note over A,C: All spans share trace-id 4bf92f35...<br/>Assembled into one trace in the backend
{{< /mermaid >}}

## What Gets Propagated

The W3C Trace Context standard defines two HTTP headers that carry trace identity across service boundaries:

**`traceparent`** carries four fields encoded in one header:
```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^  ^                                ^               ^
             version  trace-id (16 bytes, hex)  parent-span-id  flags
```

- **trace-id**: the 16-byte identifier shared by every span in the trace
- **parent-span-id**: the span ID of the calling span (makes this the parent-child link)
- **flags**: currently only the `sampled` bit (01 = record this trace, 00 = do not)

**`tracestate`** is a vendor extension slot for additional sampling or routing metadata. OpenTelemetry uses it for the `ot` key to carry sampling decisions.

## W3C Trace Context vs B3

Before W3C standardised trace context propagation in 2020, Zipkin's B3 format was dominant. You may still encounter it:

| Format | Headers | Still in use? |
|--------|---------|---------------|
| W3C Trace Context | `traceparent`, `tracestate` | Yes — the standard |
| B3 Single | `b3` | Legacy Zipkin, some older services |
| B3 Multi | `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled` | Legacy Zipkin/Jaeger |

OpenTelemetry defaults to W3C. If a service in your chain uses B3, configure the `b3` propagator alongside the default:

```python
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry import propagate

propagate.set_global_textmap(
    CompositePropagator([B3MultiFormat(), propagate.get_global_textmap()])
)
```

The composite propagator tries each format in order — it will extract from whichever header is present.

## Baggage: Passing Business Context Downstream

W3C Baggage is a companion standard that lets you propagate arbitrary key-value pairs alongside the trace context:

```
baggage: userId=abc123,tenantId=enterprise-456,featureFlag=new-checkout
```

Baggage values are available to every service downstream in the call chain. Common uses:
- Propagating user ID for log correlation without re-querying auth
- Propagating feature flag state so downstream services can tag spans with it
- Propagating tenant ID for multi-tenant cost attribution

**Cardinality warning:** Baggage values end up as span attributes in every downstream service. High-cardinality values (UUIDs, session tokens) will inflate your metric cardinality if any processor promotes baggage to attributes. Keep baggage values low-cardinality or scope them carefully.

## Where Propagation Breaks

The most common propagation failures:

**HTTP client not instrumented:** Auto-instrumentation injects headers into HTTP requests automatically. If a service makes HTTP calls via a raw client (not wrapped by the OTel HTTP instrumentation), headers are not injected. The span exists, but the child service starts a new root trace.

**Message queues:** Context does not propagate through message brokers automatically. The producer must inject trace context into message attributes or headers, and the consumer must extract it:

```python
# Producer: inject context into message attributes
carrier = {}
propagate.inject(carrier)
message.attributes["traceparent"] = carrier.get("traceparent", "")

# Consumer: extract context and make it the parent
carrier = {"traceparent": message.attributes.get("traceparent", "")}
ctx = propagate.extract(carrier)
with tracer.start_as_current_span("process-message", context=ctx):
    ...
```

**gRPC:** OTel gRPC instrumentation handles propagation via metadata. Verify both client and server interceptors are registered.

**Sampling mismatch:** If a head-based sampler on service A decides to drop the trace (sets the `sampled` flag to 0), all downstream services must respect that decision — they should not start new root traces for the same request. The `sampled` flag in `traceparent` is the contract.

## Database and External Calls

Do not propagate trace context to external systems you do not control (third-party APIs, customer-facing systems). The trace ID would leak internal infrastructure information.

For database calls, OTel database instrumentation creates child spans that remain within your trace but does not add headers to SQL queries. This is correct behaviour.

## Verifying Propagation Is Working

A healthy propagation chain produces traces where:
- Every span in the trace shares the same `trace_id`
- Parent-child relationships form a tree (no orphaned spans)
- Cross-service spans have a `span_kind` of `CLIENT` on the caller and `SERVER` on the callee
- The trace starts at the edge (load balancer or API gateway) and terminates at the deepest dependency

To check: pick a trace in your backend and verify it spans all the services a request is expected to touch. If a service is missing, its HTTP client is not instrumented or propagation headers are being stripped.

<!-- TODO: Add section on context propagation through async/worker threads -->
<!-- TODO: Add section on propagating context through AWS Lambda and cloud function invocations -->
<!-- TODO: Add worked examples for Go, Java, Node.js propagation setup -->
<!-- TODO: Add section on propagation debugging: how to inspect traceparent headers in flight -->
