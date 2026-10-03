---
title: "The Evolution of System Understanding"
date: 2026-06-07
draft: false
excerpt: "From grepping one log file to querying wide, trace-linked events: how the questions we can ask a running system changed when monoliths split apart, and why OpenTelemetry had to exist."
readtime: 5
tags: ["Observability", "OpenTelemetry", "Tracing", "Philosophy"]
references:
  - title: "A brief history of OpenTelemetry (So Far)"
    url: "https://www.cncf.io/blog/2019/05/21/a-brief-history-of-opentelemetry-so-far/"
    note: "Sigelman & McLean (CNCF, May 2019) on the OpenTracing + OpenCensus merger that formed OpenTelemetry."
  - title: "What is OpenTelemetry?"
    url: "https://opentelemetry.io/docs/what-is-opentelemetry/"
    note: "The project's own account of its origins and scope."
  - title: "OTLP — OpenTelemetry Protocol specification"
    url: "https://opentelemetry.io/docs/specs/otlp/"
    note: "The common wire protocol for traces, metrics, and logs."
  - title: "OpenTelemetry semantic conventions"
    url: "https://opentelemetry.io/docs/specs/semconv/"
    note: "The shared attribute names (http.response.status_code, cloud.region, service.version) used in the example event."
  - title: "W3C Trace Context"
    url: "https://www.w3.org/TR/trace-context/"
    note: "Defines the 16-byte trace-id and 8-byte parent-id carried in the traceparent header."
tools:
  - title: "opentelemetry-collector"
    url: "https://github.com/open-telemetry/opentelemetry-collector"
    note: "Core receive / process / export pipelines."
---

For most of computing history, understanding a running system meant reading its logs, watching its dashboards, and writing an alert for the last thing that broke you. That worked while systems were small, stable, and well understood. It stopped working over the 2010s, as the industry broke monoliths into services and the assumptions underneath traditional monitoring quietly stopped being true.

This is the short history of how we got from one to the other. If you want the definitions, [Observability vs. Monitoring](/articles/observability-vs-monitoring/) draws the line between the two words.

## The monolithic era

In a monolith, the system is one unit. A problem in the payment code shows up in the payment logs. A slow database query shows up in the query-time metric. The instrumentation strategy is obvious: monitor the things you care about, set thresholds based on what normal looks like, and alert when that changes.

The model works because failures repeat. If something broke last month, it'll probably break the same way again. You write an alert for it and move on.

The catch: it only works if you already know what can go wrong.

## When the map ran out

Split that monolith into dozens of services and the "anticipate the failure mode" model falls apart. A request crosses service boundaries, a slow dependency surfaces as an error somewhere else entirely, and every per-service dashboard stays green while users hit the wall. That failure mode gets its own walkthrough in [The dashboard was green, but the request was broken](/articles/distributed-tracing-dashboard-was-green/).

What changed wasn't only the architecture. It was what you could know in advance. A useful way to see it is as a map with four kinds of territory.

**Charted.** Failures you've already seen and instrumented. Payment success rate, transaction volume, latency thresholds. You have alerts for these, and they do their job.

**Marked.** Gaps you know about but haven't instrumented. You know regional performance varies, but latency isn't split by region. You know a traffic spike is coming, but the new checkout flow is untested. The gap is on the map. Nobody has walked it yet.

**Rumored.** Signals already hiding in your telemetry. The `payment.provider` field has been on every event for a year, and nobody has ever filtered on it. The data is there; the question isn't. This is where the fastest wins live.

**Here Be Dragons.** The failures that catch you by surprise. New interactions between services. A cascade triggered by a third-party edge case. Fraud patterns that only appear when signals combine in ways nobody expected.

Traditional monitoring covers the first tier. Most teams spend their time in the second. The fastest wins are in the third. The incidents you remember live in the fourth.

{{< obs-knowledge-tiers >}}

## The telemetry gap

The first three tiers are reachable with better instrumentation. The fourth is only reachable if your telemetry already carries enough context to answer a question nobody thought to ask. For a long time, it didn't, and it couldn't. Storage was expensive, and querying rich data at scale wasn't practical. A payment from that era usually left something like this behind:

```text
2005-06-14 09:12:00 INFO  payment success amount=49.99
```

One question: did it succeed? That was the ceiling.

A current equivalent, as a single wide event attached to a span:

```json
{
  "timestamp": "2026-06-04T09:12:00Z",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "duration_ms": 187,
  "service.name": "checkout-api",
  "service.version": "4.2.1",
  "cloud.region": "eu-west-1",
  "http.request.method": "POST",
  "http.response.status_code": 200,
  "payment.amount": 49.99,
  "payment.currency": "GBP",
  "payment.provider": "stripe",
  "payment.method": "card",
  "app.customer.tier": "premium",
  "app.auth.duration_ms": 43
}
```

The `trace_id` and `span_id` are the W3C Trace Context sizes, 32 and 16 hex characters, which is what lets this event be stitched to every other span in the same request. `service.*`, `cloud.region` and `http.*` are OpenTelemetry semantic conventions, so every backend reads them the same way. The `payment.*` and `app.*` keys are this application's own namespace, and note what's absent: no user ID, no email, nothing that identifies a person. You can segment by customer tier without carrying the customer.

Now you can ask: is this payment slow? Slow for one provider? In one region? For premium customers only? Since one release? Those are the questions that turn a "latency spiked" alert into "Stripe auth latency spiked for premium customers in eu-west-1 on 4.2.1", which is a root cause, not a symptom.

## OpenTelemetry: a shared foundation

Distributed tracing gave us the first real answer to "where did this request go?", and the [tracing article](/articles/distributed-tracing-dashboard-was-green/) covers why it took a decade to go mainstream. The practical barrier through most of the 2010s was fragmentation. Each team picked its own tracing library, its own metrics client, its own data format. Correlating signals across services meant reconciling incompatible data models, and the observability stack became operational debt of its own.

Two open projects tried to fix that, and their overlap made it worse: OpenTracing, a vendor-neutral tracing API, and OpenCensus, Google's libraries for collecting traces and metrics. In May 2019, their maintainers announced they were merging into OpenTelemetry, accepted as a CNCF sandbox project, and described it as the next major version of both. The goal they named was consolidation itself, not a shiny new feature.

What came out of it is the foundation most stacks now share: one vendor-neutral API and SDK per language for traces, metrics, and logs; one wire protocol, OTLP; one Collector to receive, process, and forward to any backend; and one set of semantic conventions so that `http.response.status_code` means the same thing everywhere. [OpenTelemetry: What It Is and How It Fits Together](/guides/opentelemetry-overview/) walks through each piece. With W3C Trace Context carrying the `traceparent` header between services (the mechanics are in the [context propagation guide](/guides/otel-context-propagation/)), the event above stops being a nice idea and becomes something you can emit from service one and still query in service thirty.

## Where the map goes next

Every step in this history bought a sharper question: did it succeed, then is the error rate rising, then which service, then why, for whom, and since which release. The move from monitored to observable is less about tools than about building systems that emit enough context to be questioned at all.

The next step is turning that context into foresight, catching the pattern before it becomes the incident. That's the argument of [Observability 1.0 meant forensics. Observability 2.0 means prevention.](/articles/what-is-observability-2-and-why-scryops/) Part of it is already running in production: continuous profiling shows which function burned the CPU inside the slow span, covered in [eBPF continuous profiling](/guides/ebpf-continuous-profiling/).
