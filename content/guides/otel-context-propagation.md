---
title: "Context Propagation: How Distributed Traces Stay Connected Across Services"
date: 2026-10-01
draft: false
excerpt: "A distributed trace is only as complete as its weakest propagation link. One hop that drops the context and the trace splits in two. W3C Trace Context and Baggage, the propagator settings that matter, and the places context gets lost — between services and inside them — in .NET, Java, Go, Python and Node."
readtime: 11
tags: ["OpenTelemetry", "Tracing", "Observability", "Best Practices"]
---

A distributed trace is not stored in one place. It is assembled from spans emitted by dozens of services, each running independently. The only thing connecting them is a trace ID, passed from service to service in HTTP headers, message metadata or gRPC metadata.

If that ID stops being passed, the trace breaks. The spans still exist, but they're orphaned, cut off from the request they were part of. [The Dashboard Was Green. The Request Was Broken.](/articles/distributed-tracing-dashboard-was-green/) shows what that costs you during an incident.

Context propagation is the mechanism that keeps the trace together. It has two halves. *Between* processes, a propagator writes the context into the outgoing request and reads it back on the other side. *Inside* a process, the runtime has to carry the current context from the code that received the request to every thread, task and callback that does work for it. Traces break at both.

{{< mermaid caption="Fig. — The traceparent header carries one trace-id hop by hop, so spans created by every service in the chain assemble into a single trace instead of orphaned fragments." >}}
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

The W3C Trace Context standard defines the two headers that carry trace identity across service boundaries.

**`traceparent`** packs four fields into one header:

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             │  │                                │                └ trace-flags
             │  │                                └ parent-id (8 bytes, hex)
             │  └ trace-id (16 bytes, hex)
             └ version
```

- **trace-id**: the identifier every span in the trace shares
- **parent-id**: the span ID of the caller's span, which is what makes the new span its child
- **trace-flags**: bit `01` is *sampled*, meaning the caller may have recorded this trace. [Trace Context Level 2](https://www.w3.org/TR/trace-context-2/), still a W3C draft, adds bit `02`, which says the trace ID is random. That's why the Java agent and the Python SDK send `03` while .NET, Go and Node send `01`. Both are valid; anything that tests the flags with `== "01"` instead of checking the bit is a bug waiting to happen.

**`tracestate`** is a list of vendor-specific entries that travel with the trace. OpenTelemetry uses its own `ot` entry there for consistent probability sampling, carrying the sampling threshold so every service in the trace can make the same keep-or-drop decision.

## Propagators: Which Headers, In Which Order

A propagator knows how to write the context into a carrier (headers, message attributes) and read it back. The standard way to choose them is the `OTEL_PROPAGATORS` environment variable:

```bash
OTEL_PROPAGATORS=tracecontext,baggage        # the default
```

The accepted values cover the formats you're likely to meet:

| Value | Headers | When you need it |
|---|---|---|
| `tracecontext` | `traceparent`, `tracestate` | Always: the W3C standard since 2020 |
| `baggage` | `baggage` | Always: W3C Baggage, see below |
| `b3` / `b3multi` | `b3` / `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled` | Zipkin-era services, some service meshes |
| `jaeger` | `uber-trace-id` | Old Jaeger clients (deprecated) |
| `xray` | `X-Amzn-Trace-Id` | AWS services that speak X-Ray (third-party propagator) |

**Not every SDK reads it, though.** In testing, the Python SDK honoured `OTEL_PROPAGATORS`, while the .NET SDK and a bare Node `NodeTracerProvider` ignored it. Elsewhere it's read by the setup layer rather than the SDK itself: the Java agent and the SDK's autoconfigure module, Node's `NodeSDK` and auto-instrumentation package, .NET's zero-code auto-instrumentation, and Go's contrib `autoprop` package. Where it isn't read, the propagator list is whatever the code sets. For .NET and Node that defaults to W3C Trace Context and Baggage, which is fine until you need B3 or X-Ray, and then you set it in code (`Sdk.SetDefaultTextMapPropagator` in .NET).

**Go is the trap.** Its global propagator is a no-op until you set one: it lists no fields and injects nothing. A Go service that creates spans perfectly well but never makes this call will start a new trace for every downstream call it makes:

```go
otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
	propagation.TraceContext{}, propagation.Baggage{},
))
```

**Mixing formats.** List several and outbound requests carry all of them. A Python service with `tracecontext,baggage,b3multi` sends `traceparent` *and* the three B3 headers on every call. Inbound, the propagators run in list order and each one that finds its headers overwrites what the previous one extracted, so **the last one wins**. In testing, a request carrying both a W3C and a B3 trace ID continued the B3 trace with `tracecontext,baggage,b3multi` and the W3C trace with `b3multi,tracecontext,baggage`. While you migrate off B3, put `tracecontext` last so the standard is the one you continue.

## Baggage: Passing Context Downstream

[W3C Baggage](https://www.w3.org/TR/baggage/) is the companion standard: a header of key-value pairs that travels alongside the trace context.

```
baggage: tenant.id=acme,feature_flag.checkout=new-flow
```

Every service downstream can read it. Typical uses are a tenant ID for cost attribution in a multi-tenant system, or a feature-flag variant so downstream services can tell which experience a request was in.

Three things trip people up:

- **Baggage is not added to spans or logs.** Reading it is your code's job. In all five SDKs tested here, a consumer that extracted `tenant.id=acme` had the baggage available in its context, and *no* attributes on its span. If you want it on every span, add a baggage span processor (the contrib packages for most languages have one) and accept what that means for attribute volume.
- **It has to be in the current context to be sent.** In Python, for example, `baggage.set_baggage()` returns a new context; until you `context.attach()` it, `inject` doesn't see it, and nothing goes on the wire.
- **It leaves your system.** Baggage rides on every outbound request that's instrumented, including calls to third-party APIs. The spec is blunt: either keep confidential information out of baggage, or make sure baggage doesn't cross trust boundaries. Never put a user ID, email or session token in it. Senders only have to propagate it intact up to 64 entries and 8,192 bytes, so it isn't a place for payloads either.

## Where Propagation Breaks Between Services

**An HTTP client that isn't instrumented.** Instrumentation libraries and agents inject headers into the clients they know about. A raw socket, an unusual HTTP library or a hand-rolled client sends the request without them, and the next service starts a new root trace.

**Message queues.** Most brokers don't carry trace context on their own. The producer has to inject it into the message's headers or attributes, and the consumer has to extract it. Inject the whole carrier, not only `traceparent`, so that `tracestate` and `baggage` travel too:

{{< langswitch >}}
```csharp
// Producer: write the current context into the message headers
var propagator = Propagators.DefaultTextMapPropagator;
propagator.Inject(new PropagationContext(Activity.Current!.Context, Baggage.Current),
    message.Headers, (headers, key, value) => headers[key] = value);

// Consumer: read it back and start the consumer span as its child
var parent = propagator.Extract(default, message.Headers,
    (headers, key) => headers.TryGetValue(key, out var v) ? new[] { v } : Array.Empty<string>());
Baggage.Current = parent.Baggage;
using var span = source.StartActivity("orders process", ActivityKind.Consumer, parent.ActivityContext);
```
```java
// Producer
TextMapPropagator propagator = openTelemetry.getPropagators().getTextMapPropagator();
propagator.inject(Context.current(), message.headers(), Map::put);

// Consumer
TextMapGetter<Map<String, String>> getter = new TextMapGetter<>() {
  public Iterable<String> keys(Map<String, String> c) { return c.keySet(); }
  public String get(Map<String, String> c, String k) { return c == null ? null : c.get(k); }
};
Context parent = propagator.extract(Context.root(), message.headers(), getter);
Span span = tracer.spanBuilder("orders process").setSpanKind(SpanKind.CONSUMER)
    .setParent(parent).startSpan();
```
```go
// Producer
carrier := propagation.MapCarrier{}
otel.GetTextMapPropagator().Inject(ctx, carrier)
msg.Headers = carrier

// Consumer
ctx := otel.GetTextMapPropagator().Extract(context.Background(), propagation.MapCarrier(msg.Headers))
ctx, span := tracer.Start(ctx, "orders process", trace.WithSpanKind(trace.SpanKindConsumer))
defer span.End()
```
```python
from opentelemetry import propagate, trace

# Producer
carrier = {}
propagate.inject(carrier)
message.headers.update(carrier)

# Consumer
ctx = propagate.extract(message.headers)
with tracer.start_as_current_span("orders process", context=ctx,
                                  kind=trace.SpanKind.CONSUMER):
    ...
```
```javascript
import { context, propagation, trace, ROOT_CONTEXT, SpanKind } from "@opentelemetry/api";

// Producer
const carrier = {};
propagation.inject(context.active(), carrier);
message.headers = { ...message.headers, ...carrier };

// Consumer
const parent = propagation.extract(ROOT_CONTEXT, message.headers);
tracer.startActiveSpan("orders process", { kind: SpanKind.CONSUMER }, parent, (span) => {
  // ...
  span.end();
});
```
{{< /langswitch >}}

Each of these was run producer-to-consumer: the consumer span came out in the same trace, as a child of the producer span, with the baggage intact.

Two details matter once real brokers are involved:

- **Header case.** HTTP headers are case-insensitive; dictionary keys aren't. Go's `HeaderCarrier` and the HTTP instrumentations normalise case, but a plain map doesn't: a Go `MapCarrier` holding `Traceparent`, or a Python dict holding `X-B3-TraceId`, extracts *nothing*, without an error, and the consumer quietly starts a new trace. If a broker or gateway changes the case of your message headers, normalise to lowercase before extracting.
- **Batches.** A consumer that processes 100 messages in one span can't have 100 parents. The messaging semantic conventions model this with span *links* to each message's context, rather than a parent. Many messaging instrumentations already do this for batch receives.

**gRPC.** The gRPC instrumentations carry context in call metadata. The usual failure is a client interceptor registered without the server one, or the reverse; check both ends.

**Serverless and managed hops.** An API gateway in front of a function normally passes `traceparent` through, so HTTP-triggered functions continue the trace when the function is instrumented. Event-triggered functions are message consumers: the context has to be in the event's message attributes, put there by the producer, and the function has to extract it. AWS services that propagate with their own `X-Amzn-Trace-Id` header need the `xray` propagator in the list on both sides of that hop.

**Sampling decisions that ignore the parent.** The default sampler is parent-based: if the caller's `traceparent` says *sampled*, the service records its span; if not, it doesn't. A service configured with a plain ratio sampler makes its own decision instead, so traces arrive with holes where its spans should be. Keep the head-sampling decision parent-based everywhere, and make keep-or-drop decisions that need the whole trace [in the Collector](/howtos/configure-collector-tail-sampling/). [Your Sampling Strategy Is Lying to You](/articles/sampling-strategy/) covers why.

## Where Propagation Breaks Inside a Service

Between the request coming in and the request going out, the context lives in the runtime: `Activity.Current` in .NET, `Context.current()` in Java, a `context.Context` value in Go, `contextvars` in Python, `AsyncLocalStorage` in Node. It follows the code as long as the runtime carries it. Here's where it didn't, in testing:

- **.NET** keeps it across `await`, `Task.Run` and `new Thread`. It's lost in the `ThreadPool.Unsafe…` APIs and in a background worker started before the request. Fix: pass the context with the work item.
- **Java with the agent** keeps it across executors and `CompletableFuture`. It's lost when work is handed over through your own queue. Fix: pass the context with the work item.
- **Java without the agent** keeps it on the same thread only; executors and `CompletableFuture.supplyAsync` lose it. Fix: wrap the executor with `Context.taskWrapping(executor)`.
- **Go** has it wherever you pass `ctx`, and nowhere else: a goroutine that uses `context.Background()` has no trace. Fix: pass `ctx`, always.
- **Python** keeps it across `asyncio` tasks. `ThreadPoolExecutor` and `threading.Thread` lose it. Fix: `contextvars.copy_context().run(fn)`, or install `opentelemetry-instrumentation-threading`.
- **Node** keeps it across `await`, timers and `setImmediate`. It's lost in a worker that drains an in-process queue. Fix: `context.bind(context.active(), fn)` when you enqueue.

The case that applies in every language is the long-lived background worker: a loop started at application start-up that pulls jobs off an in-process queue or channel. It was started outside any request, so that's the context it has. To it, an in-process queue is the same problem as a message broker, and the fix is the same: put the context in the job when you enqueue it, and restore it when you dequeue.

{{< insight bookmark >}}
**Lost context is also why logs lose their trace IDs.** A log line written on a thread or task that lost the context has no span to read the IDs from. If [trace IDs are missing from some of your logs](/howtos/wire-trace-ids-into-logs/#closing-the-loop--verify-its-working) but not others, look for one of the hand-offs in the table above.
{{< /insight >}}

## Trust Boundaries

Propagation crosses your system's edges in both directions, and each direction deserves a decision.

**Outbound, to third parties.** Instrumented clients add `traceparent`, `tracestate` and `baggage` to every call, including calls to payment providers and partner APIs. A trace ID is random and says little; baggage can say a great deal. Either keep baggage free of anything you wouldn't send a third party, or strip it on egress.

**Inbound, from the public internet.** A `traceparent` from a browser or an external client is input you didn't create. Continuing it lets a caller choose your trace IDs and, through the sampled flag, influence what you record. Many teams start a fresh trace at the edge for untrusted callers, and link to the incoming context instead of continuing it, so the connection isn't lost.

**Databases.** Database instrumentation creates client spans for each query within your trace, but doesn't send the context to the database. That's usually what you want. Some instrumentations can optionally add the `traceparent` as a SQL comment (the *sqlcommenter* format) so that slow-query logs on the database side can be traced back to the request; turn it on deliberately, because it changes the query text.

## Debugging Propagation in Flight

When a trace splits, find the hop where the context disappeared:

1. **Send a trace ID you'll recognise.** Make the request yourself with a hand-written `traceparent`, then search your backend for that ID:

   ```bash
   curl -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
        https://staging.example.internal/checkout
   ```

   Every service that shows up under `4bf92f35…` received the context; the first one missing is where to look.
2. **Look at the headers on the wire.** Point the service's downstream URL at an echo endpoint, or log incoming request headers at the receiving end for a few minutes. If `traceparent` isn't there, the sender isn't injecting it: an uninstrumented client, a missing Go propagator, a context lost on the way to the client call. If it is there and the receiver still starts a new trace, the receiver isn't extracting it: no server instrumentation, or a different propagator list.
3. **Read the span kinds.** A healthy hop is a `CLIENT` span on the caller with a `SERVER` span on the callee as its child, or `PRODUCER` and `CONSUMER` across a queue. A `SERVER` or `CONSUMER` span with no parent, in the middle of what should be one request, is the broken link.

## Verifying Propagation Is Working

A healthy propagation chain produces traces where:

- Every span in the trace shares the same trace ID
- Parent-child relationships form one tree, with no orphaned spans
- Each cross-service hop is a `CLIENT`/`SERVER` or `PRODUCER`/`CONSUMER` pair
- The trace starts at the edge (the load balancer or API gateway) and reaches the deepest dependency the request touched

To check, pick a trace in your backend and confirm that it includes every service the request was expected to touch. If one is missing, work through the debugging steps above for the hop leading into it.
