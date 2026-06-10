---
title: "How to Configure OTel Collector Tail Sampling"
date: 2026-05-26
draft: false
excerpt: "Move from flat probabilistic sampling to intelligent tail-based sampling in the OTel Collector — keeping 100% of errors and slow traces while dropping the noise that doesn't earn its storage cost."
readtime: 8
tags: ["OpenTelemetry", "Sampling", "Collector", "Tracing", "How-to"]
---

> "Don't keep what happened. Keep what matters. The rest is just noise you're paying to store."
> — A Platform Engineer, Reviewing the Cloud Bill

Your current sampling strategy is probably making a decision before it has any information to act on. Head-based sampling — the default — decides whether to keep a trace at the moment the first span starts, before you know if the request will succeed, fail, or take ten times longer than expected. You end up with a random 5% sample, not a representative one.

Tail-based sampling waits until the trace is complete, then decides. Errors: keep. Slow requests: keep. Health check noise: mostly discard.

## What you'll need

- OTel Collector v0.90+ (`otelcol-contrib` distribution — the tail sampling processor is a community component)
- Services sending traces to the Collector via OTLP
- Basic familiarity with the Collector's YAML config format

## First, a Decision About Architecture

Tail sampling has one structural requirement that head-based sampling doesn't: all spans for a given trace must arrive at the same Collector instance. The sampler needs to see the complete trace before it can make a decision. If spans from the same trace scatter across multiple Collector instances behind a load balancer, each instance sees an incomplete picture and can't evaluate correctly.

You have two valid paths:

**Single Collector** — the right choice for most services. No routing complexity. Handles roughly 50k concurrent traces comfortably in memory. Start here.

**Collector cluster with routing** — for high-volume services where one instance isn't enough. A first-tier Collector routes spans by trace ID to a second-tier tail-sampling Collector, ensuring all spans for a trace land together. Uses the `loadbalancingexporter` with `routing_key: traceID`. Covered at the end of this guide.

## Step 1 — Confirm You Have the Right Build

The tail sampling processor ships in `otelcol-contrib`, not the core `otelcol` binary. Verify it's available:

```bash
otelcol-contrib components | grep tail_sampling
```

If you get no output, download the contrib distribution:

```bash
# https://github.com/open-telemetry/opentelemetry-collector-releases/releases
# Look for otelcol-contrib_<version>_<platform>
```

## Step 2 — Tell the Collector What to Keep

Replace your existing `probabilistic_sampler` processor with `tail_sampling`. The configuration below covers the most common production policies — annotated so you can tune them for your traffic profile:

```yaml
# collector.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  tail_sampling:
    # How long to wait after the last span before making the decision.
    # 10s covers most request lifetimes. Increase for async jobs or
    # multi-step workflows that take longer to complete.
    decision_wait: 10s

    # Max traces to hold in memory simultaneously.
    # At ~5KB per trace, 50k traces ≈ 250MB. Size to your available memory.
    num_traces: 50000

    # Used for internal buffer sizing — set to your expected peak TPS.
    expected_new_traces_per_sec: 500

    policies:
      # ── Always keep ──────────────────────────────────────────────────

      # Every trace with an error span — these are your crime scenes.
      - name: errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      # Any trace where a span took over 1 second (tune to your SLO threshold).
      - name: slow-traces
        type: latency
        latency:
          threshold_ms: 1000

      # All traces for high-value customers — never sample these away.
      - name: high-value-customers
        type: string_attribute
        string_attribute:
          key: customer.tier
          values: [premium, enterprise]

      # ── Reduce noise ─────────────────────────────────────────────────

      # Health checks fire constantly and almost never carry useful signal.
      # Keep 1% as a statistical baseline; drop the rest.
      - name: health-check-noise
        type: and
        and:
          and_sub_policy:
            - name: is-health-endpoint
              type: string_attribute
              string_attribute:
                key: http.route
                values: [/health, /ready, /live, /metrics, /ping]
            - name: rate-limit
              type: probabilistic
              probabilistic:
                sampling_percentage: 1

      # ── Baseline ──────────────────────────────────────────────────────

      # 5% of everything else — enough for statistical analysis and
      # capacity planning, without storing every successful cache hit.
      - name: baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

  batch:
    timeout: 1s
    send_batch_size: 1024

exporters:
  otlp/backend:
    endpoint: your-backend:4317

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [tail_sampling, batch]
      exporters: [otlp/backend]
```

Policy order does not affect correctness — the Collector evaluates all policies independently and keeps a trace if any single policy returns sampled. An error trace matched by the `errors` policy will be kept regardless of where `baseline` appears in the list. Order is a readability convention, not a functional requirement.

## Step 3 — Sanity-Check Your Policies

Before deploying, map your service's traffic types against the policies you've defined:

| Traffic type | Policy that handles it | Expected keep rate |
|---|---|---|
| 5xx responses | `errors` | 100% |
| Requests > 1s latency | `slow-traces` | 100% |
| Premium customer requests | `high-value-customers` | 100% |
| `/health`, `/ready` etc. | `health-check-noise` | 1% |
| Everything else | `baseline` | 5% |

If your service has other high-value traffic — checkout flows, payment transactions, canary deployments — add explicit policies for them above the `baseline` rule. Any trace type you don't name explicitly will land in the 5% sample.

{{< insight lightbulb >}}
**The `and` policy type** combines conditions with logical AND. Here it limits health checks to 1% *without* that rate-limiter affecting the `errors` policy above it. Without the `and`, a simple `probabilistic` policy at 1% would apply to everything, including errors. Policy order and type work together — think through the interaction before deploying.
{{< /insight >}}

## Step 4 — Watch the Buffer

Tail sampling holds traces in memory until `decision_wait` expires. Restart the Collector and give it a few minutes of real traffic, then check the self-monitoring metrics:

```bash
# If the Collector is exporting its own metrics to Prometheus:
curl http://localhost:8888/metrics | grep tail_sampling
```

Three numbers to pay attention to:

**`otelcol_processor_tail_sampling_sampling_trace_dropped_count`** — traces dropped because `num_traces` was exceeded. If this is non-zero under normal load, increase `num_traces` or reduce `decision_wait`.

**`otelcol_processor_tail_sampling_sampling_decision_timer_latency`** — how long decisions are taking. Should stay under 100ms.

**Process memory** — should stabilise at roughly `num_traces × average_trace_size`. If it keeps growing, you likely have spans arriving with trace IDs that never complete — orphaned spans that stay in the buffer until eviction.

## Step 5 (Optional) — Scaling to Multiple Collectors

When one Collector instance can't hold the buffer you need, add a routing layer in front. The `loadbalancingexporter` handles trace-ID affinity automatically. The topology looks like this:

{{< mermaid >}}
flowchart LR
    S1[Service A] --> LB
    S2[Service B] --> LB
    S3[Service C] --> LB

    subgraph Tier1["Tier 1 — Load Balancer Collector"]
        LB["loadbalancingexporter<br/>(routing_key: traceID)"]
    end

    subgraph Tier2["Tier 2 — Tail Sampling Collectors"]
        TS0[tail-sampler-0<br/>tail_sampling processor]
        TS1[tail-sampler-1<br/>tail_sampling processor]
        TS2[tail-sampler-2<br/>tail_sampling processor]
    end

    LB -->|all spans for trace A| TS0
    LB -->|all spans for trace B| TS1
    LB -->|all spans for trace C| TS2

    TS0 --> Backend[(Tracing Backend)]
    TS1 --> Backend
    TS2 --> Backend
{{< /mermaid >}}

```yaml
# Tier 1: Load balancer Collector
# Receives all spans, routes by trace ID so all spans for one trace
# always land on the same Tier 2 instance.

exporters:
  loadbalancing:
    protocol:
      otlp:
        tls:
          insecure: true
    resolver:
      static:
        hostnames:
          - tail-sampler-0:4317
          - tail-sampler-1:4317
          - tail-sampler-2:4317
    routing_key: traceID    # ← the critical setting

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [loadbalancing]
```

Each downstream Collector (`tail-sampler-0`, `tail-sampler-1`, `tail-sampler-2`) runs the full `tail_sampling` processor config from Step 2. The `loadbalancingexporter` handles rehashing when instances are added or removed — you don't need to implement consistent hashing yourself.

## Did It Work?

After deploying, make three types of requests: one that returns an error, one that's deliberately slow (add a `time.sleep(2)` to a handler temporarily), and several fast successful ones. Then check your tracing backend:

- **Error traces should appear at 100%** — search by `status=error` and confirm they're all there
- **Slow traces should appear at 100%** — search by latency > your threshold
- **Fast successful traces should appear at roughly 5%** — the volume should be dramatically lower than your actual request rate

If errors are being dropped, check that your error policy condition matches the attribute your service actually sets — `http.status_code` for HTTP services, `rpc.grpc.status_code` for gRPC, or `otel.status_code = "ERROR"` if you set status explicitly. Policy order does not affect which traces are kept; all policies are evaluated independently.

## Your Collector Now Samples on Evidence, Not Chance

Your Collector is now making sampling decisions based on what happened in a trace, not a coin flip at trace start. Errors are preserved. Slow traces are preserved. Health check noise is nearly absent. Your baseline gives you statistical coverage for capacity planning and trend analysis.

The storage bill goes down. The diagnostic signal goes up. Both at once.

For the thinking behind why this matters, [Your Sampling Strategy Is Lying to You](/guides/sampling-strategy/) has the full argument.
