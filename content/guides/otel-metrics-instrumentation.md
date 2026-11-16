---
title: "OTel Metrics Instrumentation: Choosing the Right Instrument for the Job"
date: 2026-11-16
draft: false
excerpt: "OpenTelemetry has seven metric instruments. Pick the wrong one and you get data that looks fine and answers the wrong question. Here's what Counter, Histogram, Gauge, UpDownCounter, and the observable variants each measure, and what they cost you in time series."
readtime: 8
tags: ["OpenTelemetry", "Metrics", "Observability", "Best Practices"]
card:
  title: "Choosing the Right OTel Metric Instrument"
---

The instrument you pick decides which questions you can answer later. A Counter gives you a rate. A Histogram gives you a distribution. A Gauge gives you a current value. Use a Counter where you needed a Histogram and you can tell that traffic changed, but not whether a few requests got very slow or all of them got slightly slow.

That's not a small difference. It decides whether your p95 latency alert can exist at all.

The Python samples below were run against `opentelemetry-sdk` **1.45.2**. Metric and attribute names follow semantic conventions **v1.45.0**.

## The seven instruments

There are four synchronous instruments, which you call from your code as things happen. Three of them have an asynchronous twin, which the SDK calls on a timer.

| Synchronous | Asynchronous |
|---|---|
| Counter | ObservableCounter |
| UpDownCounter | ObservableUpDownCounter |
| Gauge | ObservableGauge |
| Histogram | none |

### Counter

It only goes up. It starts again from zero when the process restarts.

**Use it for:** counting things that happen. Requests, errors, bytes sent, orders placed.

**What you get:** a rate. The raw total is rarely what you look at. You look at `rate()` in PromQL, or the equivalent in your backend.

```python
orders_placed = meter.create_counter(
    "orders.placed",
    unit="{order}",
    description="Orders placed",
)

# Where the order is confirmed
orders_placed.add(1, {"payment.method": "card"})
```

**Anti-pattern:** a Counter for a value that can go down, like active connections or queue depth. That's an UpDownCounter.

You don't need a counter for HTTP requests. The HTTP conventions define one histogram, `http.server.request.duration`, and its count *is* the request count.

### Histogram

It records a distribution. Each measurement lands in a bucket, and the buckets are what make percentiles possible.

**Use it for:** latency, request size, response size. Anything where the shape matters, not only the total.

```python
request_duration = meter.create_histogram(
    "http.server.request.duration",
    unit="s",
    description="HTTP request duration",
    explicit_bucket_boundaries_advisory=[
        0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10
    ],
)

# One measurement, in seconds
request_duration.record(0.142, {"http.request.method": "GET", "http.route": "/orders"})
```

**What you get:** in Prometheus, three kinds of series: `_bucket`, `_sum`, and `_count`. From those you compute p50, p95, p99, and the average.

**Set the buckets. The defaults will bite you.** The SDK's default boundaries are `[0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000]`. Those numbers have no unit. They were chosen with milliseconds in mind, but the conventions now record durations in seconds. Record a 30ms request as `0.03` against the defaults and it lands in the 0-to-5 bucket, along with every other request you'll ever serve. Your p99 becomes a guess.

The `explicit_bucket_boundaries_advisory` argument above is the fix at the source. Those are the boundaries the HTTP conventions recommend. If you don't own the instrument, because a library created it, override the buckets with a View when you build the provider:

```python
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

# For an operation where p99 is usually under 200ms
latency_view = View(
    instrument_name="checkout.duration",
    aggregation=ExplicitBucketHistogramAggregation(
        boundaries=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5]
    ),
)

provider = MeterProvider(metric_readers=[reader], views=[latency_view])
```

A View wins over the advisory boundaries when both are set.

### Gauge

It records the current value of something. It isn't additive: two replicas reporting a gauge don't add up to anything meaningful.

**Use it for:** a current reading you're handed, as opposed to one you go and fetch. Replication lag reported by a heartbeat, a temperature, a configured limit.

```python
replication_lag = meter.create_gauge(
    "replication.lag",
    unit="s",
    description="Replication lag reported by the last heartbeat",
)

# Whenever a heartbeat arrives
replication_lag.set(1.8, {"db.replica": "replica-2"})
```

**Anti-pattern one:** a Gauge for something that only goes up. That's a Counter.

**Anti-pattern two:** a Gauge for a ratio you could derive. Don't export a cache hit ratio. Export two counters, hits and misses, and divide in the query. You can re-aggregate counters across replicas and time windows. You can't average a ratio and get the right answer.

### UpDownCounter

A Counter that can go down. It tracks how many of something exist right now.

**Use it for:** active connections, queue depth, items in a pool, requests in flight.

```python
active_requests = meter.create_up_down_counter(
    "http.server.active_requests",
    unit="{request}",
    description="Number of HTTP requests currently being processed",
)

# When a request arrives
active_requests.add(1, {"http.request.method": "GET"})

# When it completes
active_requests.add(-1, {"http.request.method": "GET"})
```

**What you get:** the current total, and unlike a Gauge you can sum it across replicas. Alert on it climbing past your normal ceiling and you catch a pile-up before latency shows it.

The attributes on the `-1` must match the attributes on the `+1`. If they don't, one series climbs forever and another sinks below zero.

**UpDownCounter or Gauge?** Ask whether adding the values from two replicas makes sense. Queue depth across two workers: yes, so UpDownCounter. CPU utilisation across two hosts: no, so Gauge.

### Observable variants

Counter, UpDownCounter, and Gauge each have an observable form. You don't call it. You register a callback, and the SDK calls it each time it collects. There's no observable Histogram.

**Use them for:** values that already exist somewhere and that you read on a schedule. Pool sizes, process memory, anything kept by a library or the operating system.

```python
from opentelemetry.metrics import Observation

def observe_idle_connections(options):
    yield Observation(
        db_pool.idle_count(),
        {
            "db.client.connection.pool.name": "primary",
            "db.client.connection.state": "idle",
        },
    )

meter.create_observable_up_down_counter(
    "db.client.connection.count",
    callbacks=[observe_idle_connections],
    unit="{connection}",
    description="Connections in the pool, by state",
)
```

The callback runs on the collection interval, off the request path. Keep it fast anyway. A slow callback holds up collection for every other metric.

## Which instrument

| What you're measuring | Instrument |
|----------------------|-----------|
| Requests received | Histogram of duration (its count is the request count) |
| Errors, orders, bytes transferred | Counter |
| Request latency | Histogram |
| Response size | Histogram |
| GC pause duration | Histogram |
| Requests in flight | UpDownCounter |
| Queue depth | UpDownCounter |
| Pool connections (polled) | ObservableUpDownCounter |
| CPU utilisation | ObservableGauge |
| Memory in use | ObservableUpDownCounter |
| A reading pushed to you | Gauge |

## Cardinality: what a histogram really costs

Every unique combination of attribute values is a new time series. A histogram multiplies that, because each combination doesn't make one series. In Prometheus it makes one series per bucket boundary, one more for the `+Inf` bucket, plus `_sum` and `_count`.

So the cost is `(boundaries + 3) × combinations`. Ten boundaries and one attribute with 100 values: 13 × 100 = 1,300 series. Add a second attribute with 50 values and you have 5,000 combinations, so 13 × 5,000 = 65,000 series. From one instrument.

Rules for metric attributes:

- Never use unbounded values: user IDs, request IDs, email addresses, full URLs.
- Prefer small closed sets: HTTP method, route template, status code.
- Count the combinations before you ship, not after the bill arrives.

```python
# Good: bounded attributes
request_duration.record(elapsed, {
    "http.request.method": "GET",        # a handful of values
    "http.route": "/v1/orders/{id}",     # the template, not the actual path
    "http.response.status_code": 200,    # a few dozen values
})

# Dangerous: unbounded attributes
request_duration.record(elapsed, {
    "url.full": request.url,             # a new series per URL
    "user.id": user_id,                  # a new series per user
})
```

Older examples use `http.method` and `http.status_code`. Both are deprecated. The current names are `http.request.method` and `http.response.status_code`.

## Be selective

Instrument every function and you get a firehose, not observability. Put instruments where they earn their series:

- Service boundaries: inbound requests and outbound calls.
- Operations with variable latency: database queries, external APIs, cache lookups.
- Business events your SLOs care about: orders, payments, sign-ins.
- Signs of exhaustion: queue depth, pool usage, memory pressure.

Internal helpers and pure computation rarely need a metric. If your framework's instrumentation already emits `http.server.request.duration`, don't build your own copy next to it. Fewer, sharper metrics beat more of them.

<!-- TODO: Add section on Views for renaming and attribute filtering -->
<!-- TODO: Add section on exemplars: linking metric anomalies back to specific traces -->
<!-- TODO: Add worked examples for Go, Java, Node.js, .NET metric APIs -->
<!-- TODO: Add section on OTLP Metrics temporality: Delta vs Cumulative and when each applies -->
<!-- TODO: Add section on exponential histograms as the alternative to choosing boundaries -->
