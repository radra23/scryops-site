---
title: "OTel Metrics Instrumentation: Choosing the Right Instrument for the Job"
date: 2026-06-10
draft: true
excerpt: "OpenTelemetry defines six metric instrument types. Using the wrong one produces data that looks correct but answers the wrong questions. A guide to Counter, Histogram, Gauge, UpDownCounter, and their observable variants — what each measures, when to use it, and what it produces in your backend."
readtime: 9
tags: ["OpenTelemetry", "Metrics", "Observability", "Best Practices"]
---

The metric instrument you choose determines what questions you can answer later. A Counter produces a rate. A Histogram produces a distribution. A Gauge produces a current value. Using a Counter where you need a Histogram means you can tell your request volume changed — but not whether the slowdown was a few very slow requests or all requests slowing slightly.

This is not a subtle difference. It determines whether your p95 latency alert can exist.

## The Six Instruments

### Counter

Monotonically increasing. Only goes up. Resets to zero on restart.

**Use for:** counting occurrences — requests, errors, bytes sent, tasks completed.

**What the backend produces:** a rate (using `rate()` in PromQL, or `derivative` in other backends). The raw count is rarely the useful view — the rate per second or per minute is.

```python
requests_total = meter.create_counter(
    "http.server.requests",
    unit="{request}",
    description="Total HTTP requests received"
)

# In request handling code
requests_total.add(1, {"http.method": "GET", "http.route": "/orders"})
```

**Anti-pattern:** using a Counter for a value that can go down (active connections, queue depth). Use `UpDownCounter` instead.

### Histogram

Records a distribution of measurements. Each observation is bucketed, enabling percentile calculations.

**Use for:** latency, request sizes, response sizes — anything where the distribution matters, not just the total.

```python
request_duration = meter.create_histogram(
    "http.server.request.duration",
    unit="s",
    description="HTTP request duration"
)

# Record a single observation (in seconds)
request_duration.record(0.142, {"http.method": "GET", "http.route": "/orders"})
```

**What the backend produces:** `_bucket` (the histogram itself), `_sum` (total of all values), `_count` (number of observations). From these you can compute p50, p95, p99, and average latency.

**Bucket configuration:** the default OTel buckets (`[0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000]` ms) are often wrong for your service. A service with p99 latency of 50ms needs finer buckets below 100ms. Configure explicit boundaries for your use case:

```python
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

# For a service where p99 is typically under 200ms
latency_view = View(
    instrument_name="http.server.request.duration",
    aggregation=ExplicitBucketHistogramAggregation(
        boundaries=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5]
    )
)
```

### Gauge

Records the current value of something at the moment of measurement. Not additive — two instances reporting a gauge are not summed.

**Use for:** current state — CPU usage, memory usage, connection pool size, cache hit ratio at this moment. Unlike a counter, there is no meaningful rate.

```python
cache_hit_ratio = meter.create_gauge(
    "cache.hit.ratio",
    unit="1",
    description="Current cache hit ratio (0.0–1.0)"
)

# Set the current value whenever it changes
cache_hit_ratio.set(0.87, {"cache.type": "redis"})
```

**Anti-pattern:** using a Gauge for something that should be a Counter. If the value only goes up over time, it's a Counter.

### UpDownCounter

Like a Counter but can decrease. Tracks values with a net direction.

**Use for:** active connections, queue depth, items in a pool, concurrent requests in flight.

```python
active_requests = meter.create_up_down_counter(
    "http.server.active_requests",
    unit="{request}",
    description="Number of HTTP requests currently being processed"
)

# Increment when request arrives
active_requests.add(1, {"http.route": "/orders"})

# Decrement when request completes
active_requests.add(-1, {"http.route": "/orders"})
```

**What the backend produces:** the current sum. You can alert on `active_requests > 500` to detect request pile-ups before they affect latency.

### Observable Variants

Each of the above has an observable (asynchronous) variant: `ObservableCounter`, `ObservableGauge`, `ObservableUpDownCounter`. Instead of being called synchronously in your code, you register a callback that is invoked when the SDK collects metrics.

**Use observable variants for:** values that are expensive to compute, values you read from an external source, or system-level metrics you poll rather than increment.

```python
def collect_connection_pool_size(options):
    current_size = db_pool.size()
    yield Observation(current_size, {"pool": "primary"})

meter.create_observable_gauge(
    "db.client.connections.idle",
    callbacks=[collect_connection_pool_size],
    unit="{connection}",
    description="Number of idle database connections in the pool"
)
```

The SDK calls `collect_connection_pool_size` on each collection interval without blocking request handling.

## Instrument Selection Guide

| What you are measuring | Instrument |
|----------------------|-----------|
| Requests received | Counter |
| Errors occurred | Counter |
| Bytes transferred | Counter |
| Request latency | Histogram |
| Response size | Histogram |
| Active connections | UpDownCounter |
| Queue depth | UpDownCounter |
| Items in cache | UpDownCounter |
| CPU usage (current) | ObservableGauge |
| Memory used (current) | ObservableGauge |
| GC pause duration | Histogram |
| Pool size (polled) | ObservableGauge |

## Attribute Cardinality and Metrics Cost

Every unique combination of attribute values creates a new time series — and a histogram is worse than it looks, because each attribute combination doesn't produce one series, it produces one series per bucket boundary *plus* `_sum` and `_count`: `(buckets + 2) × combinations`. A histogram with 10 bucket boundaries and one attribute with 100 values creates (10 + 2) × 100 = 1,200 time series. Add a second attribute with 50 values: 100 × 50 = 5,000 combinations, so (10 + 2) × 5,000 = 60,000 time series.

Rules for metric attributes:
- Never use unbounded values: user IDs, request IDs, email addresses, full URLs
- Prefer enums and small closed sets: HTTP method (8 values), HTTP route (finite), status code (50 values)
- When in doubt, benchmark cardinality before shipping to production

```python
# Good: low-cardinality attributes
requests_total.add(1, {
    "http.method": "GET",             # ~8 values
    "http.route": "/v1/orders/{id}",  # template, not actual path
    "http.response.status_code": 200  # ~50 values
})

# Dangerous: high-cardinality attributes
requests_total.add(1, {
    "url.full": request.url,          # unbounded — will explode cardinality
    "user.id": user_id,               # unbounded
})
```

## Be Selective

Instrumenting every function and every variable produces a firehose of data, not observability. Focus on the operations and decision points that have diagnostic value:

- Service boundaries (inbound requests, outbound calls)
- Operations with variable latency (database queries, external API calls, cache lookups)
- Business events that matter for SLOs (order creation, payment processing, authentication)
- Resource exhaustion signals (queue depth, connection pool usage, memory pressure)

Internal utilities, pure computations, and simple data transformations rarely need instrumentation. The signal-to-noise ratio of your metrics is as important as their accuracy.

<!-- TODO: Add section on Views for renaming, aggregation change, and attribute filtering -->
<!-- TODO: Add section on exemplars: linking metric anomalies back to specific traces -->
<!-- TODO: Add worked examples for Go, Java, Node.js, .NET metric APIs -->
<!-- TODO: Add section on OTLP Metrics temporality: Delta vs Cumulative and when each applies -->
