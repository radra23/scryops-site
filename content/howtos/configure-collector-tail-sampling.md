---
title: "How to Configure OTel Collector Tail Sampling"
date: 2026-09-29
draft: false
excerpt: "Move from flat probabilistic sampling to tail-based sampling in the OTel Collector. Keep every error and slow trace, cut health-check noise to 1%, and check that the Collector is doing what you think."
readtime: 9
tags: ["OpenTelemetry", "Sampling", "Collector", "Tracing", "How-to"]
---

Head-based sampling, the SDK default when you sample at all, decides whether to keep a trace the moment its first span starts. That's before anyone knows whether the request will succeed, fail, or take ten times longer than usual. A random 5% is a fair slice of your traffic, and that's exactly the trouble: it's mostly fast successes, and the rare errors and slow requests you actually need are as likely to be dropped as anything else.

Tail-based sampling waits, then decides. Errors: keep. Slow requests: keep. Health-check noise: mostly drop. This how-to sets that up in the OpenTelemetry Collector and shows you how to check it's working.

## What You'll Need

- The `otelcol-contrib` distribution of the Collector. The `tail_sampling` processor lives there, not in the core build. It's Beta for traces.
- Services sending traces to the Collector over OTLP
- Basic familiarity with the Collector's YAML config

Every config on this page was loaded into `otelcol-contrib` 0.161.0, and the Step 2 policies were tested with 9,600 labelled test traces.

## First, a Decision About Architecture

Tail sampling has one structural requirement that head-based sampling doesn't: every span of a trace has to reach the same Collector instance. If spans from one trace scatter across several Collectors behind a load balancer, each one sees part of the trace and judges it on half the evidence.

You've got two valid paths:

**A single Collector** is the right start for most services. There's no routing to set up. How many traces it can hold depends on your trace size and your memory, and `num_traces` sets the cap.

**A two-tier cluster** is for when one instance can't hold the buffer you need. A first tier of Collectors routes spans by trace ID to a second tier of tail-sampling Collectors, so every span of a trace lands in the same place. It uses the `loadbalancingexporter` with `routing_key: traceID`. Step 5 covers it.

## Step 1: Confirm You Have the Right Build

Check that your Collector includes the processor:

```bash
otelcol-contrib components | grep tail_sampling
```

If you run the Collector in a container, use the contrib image, `otel/opentelemetry-collector-contrib`, and check it the same way:

```bash
docker run --rm otel/opentelemetry-collector-contrib:0.161.0 components | grep tail_sampling
```

No output means you're on the core build. Get `otelcol-contrib` from the [Collector releases page](https://github.com/open-telemetry/opentelemetry-collector-releases/releases).

## Step 2: Tell the Collector What to Keep

Replace any `probabilistic_sampler` processor with `tail_sampling`. This config covers the common production policies, with notes so you can tune them to your traffic:

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
  # First in the pipeline: refuse data before the buffer eats all your memory.
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 20

  tail_sampling:
    # How long to wait after a trace's first span arrives before deciding.
    # Set it longer than your slowest normal request. Spans that arrive
    # after the decision miss it.
    decision_wait: 10s

    # Most traces held in memory at once. Memory use is roughly
    # num_traces × your average trace size, so measure yours.
    num_traces: 50000

    # Used to size internal buffers. Set it near your peak new traces per second.
    expected_new_traces_per_sec: 500

    policies:
      # ── Always keep ──────────────────────────────────────────────────

      # Every trace with a span whose status is Error.
      - name: errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      # Any trace that runs longer than 1 second (tune to your SLO).
      - name: slow-traces
        type: latency
        latency:
          threshold_ms: 1000

      # Every trace for high-value customers.
      - name: high-value-customers
        type: string_attribute
        string_attribute:
          key: customer.tier
          values: [premium, enterprise]

      # ── Health checks: keep 1% ───────────────────────────────────────

      - name: health-checks
        type: and
        and:
          and_sub_policy:
            - name: is-health-endpoint
              type: string_attribute
              string_attribute:
                key: http.route
                values: [/health, /ready, /live, /metrics, /ping]
            - name: one-percent
              type: probabilistic
              probabilistic:
                sampling_percentage: 1

      # ── Everything else: keep 5% ─────────────────────────────────────

      # The invert_match excludes health checks. Without it, this policy
      # would keep 5% of them too, and the 1% above would do nothing.
      - name: baseline
        type: and
        and:
          and_sub_policy:
            - name: not-health-endpoint
              type: string_attribute
              string_attribute:
                key: http.route
                values: [/health, /ready, /live, /metrics, /ping]
                invert_match: true
            - name: five-percent
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
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp/backend]
```

The OTLP exporter uses TLS by default. If your backend really is plaintext on a trusted network, add `tls: {insecure: true}` under `otlp/backend`.

Policy order doesn't matter. The Collector evaluates every policy for every trace and keeps the trace if any single policy says yes. An error trace matched by `errors` is kept wherever `baseline` sits in the list. The order is there for you to read, not for the Collector.

{{< insight lightbulb >}}
**Why `baseline` has to exclude health checks.** Because any policy can keep a trace, a plain 5% `baseline` would keep 5% of health checks on its own, and the 1% policy would change nothing. We tested exactly that: health checks came through at 4.7%, not 1%. The `invert_match` inside the `and` takes them out of `baseline`, and then the 1% is real. Failing health checks are still kept in full, because `errors` gets its own vote.
{{< /insight >}}

## Step 3: Sanity-Check Your Policies

Before you deploy, map your traffic against the policies. Here's what this config actually kept when we sent it 9,600 labelled test traces:

| Traffic type | Policy that keeps it | Measured keep rate |
|---|---|---|
| Span status Error | `errors` | 100% |
| Requests over 1s | `slow-traces` | 100% |
| Premium customers | `high-value-customers` | 100% |
| `/health` and friends, succeeding | `health-checks` | 1.2% |
| `/health` and friends, failing | `errors` | 100% |
| Everything else | `baseline` | 4.9% |

The probabilistic rates wobble a little around 1% and 5% because they're random samples. If your service has other traffic that matters, such as checkout flows, payments or canary deployments, give it an explicit policy. Anything you don't name lands in the 5%.

## Step 4: Watch the Buffer

Tail sampling holds traces in memory until `decision_wait` runs out. Restart the Collector, give it a few minutes of real traffic, and check its own metrics. By default the Collector serves them on port 8888:

```bash
curl -s http://localhost:8888/metrics | grep tail_sampling
```

Three things to watch:

**`otelcol_processor_tail_sampling_sampling_trace_dropped_too_early`** counts traces evicted from the buffer before a decision was made, because `num_traces` filled up. If it isn't zero under normal load, raise `num_traces` or lower `decision_wait`.

**`otelcol_processor_tail_sampling_sampling_traces_on_memory`** is how many traces are buffered right now. It should level off. If it keeps climbing, spans are arriving faster than decisions clear them.

**`otelcol_processor_tail_sampling_sampling_decision_timer_latency`** is a histogram of how long each round of decisions takes. Watch for it creeping up as you add policies.

## Step 5 (Optional): Scale to Multiple Collectors

When one Collector can't hold the buffer you need, put a routing tier in front. The `loadbalancingexporter` keeps each trace together. The topology looks like this:

{{< mermaid >}}
flowchart TB
    S1[Service A] --> LB
    S2[Service B] --> LB
    S3[Service C] --> LB

    subgraph Tier1["Tier 1: load-balancing Collector"]
        LB["loadbalancingexporter<br/>(routing_key: traceID)"]
    end

    subgraph Tier2["Tier 2: tail-sampling Collectors"]
        TS0[tail-sampler-0<br/>tail_sampling<br/>processor]
        TS1[tail-sampler-1<br/>tail_sampling<br/>processor]
        TS2[tail-sampler-2<br/>tail_sampling<br/>processor]
    end

    LB -->|all spans<br/>of trace A| TS0
    LB -->|all spans<br/>of trace B| TS1
    LB -->|all spans<br/>of trace C| TS2

    TS0 --> Backend[(Tracing Backend)]
    TS1 --> Backend
    TS2 --> Backend
{{< /mermaid >}}

```yaml
# Tier 1: load-balancing Collector
# Receives every span and routes by trace ID, so all spans of one trace
# always reach the same Tier 2 instance.

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  loadbalancing:
    routing_key: traceID    # ← the critical setting
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

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [loadbalancing]
```

Each Tier 2 Collector runs the full config from Step 2. The `loadbalancingexporter` rebalances when instances come and go, so you don't have to build consistent hashing yourself. On Kubernetes, swap the `static` list for the exporter's `k8s` or `dns` resolver pointed at the Tier 2 service, so new replicas join without a config change.

## Did It Work?

After deploying, send three kinds of request: one that fails, one that's deliberately slow (add a `time.sleep(2)` to a handler for a few minutes), and a batch of fast successful ones. Then check your tracing backend:

- **Failed requests should all be there.** Search for error status and confirm none are missing.
- **Slow requests should all be there.** Search for traces over your latency threshold.
- **Fast successful requests should show up at roughly 5%.** The volume should be far below your real request rate.

If errors go missing, check how your instrumentation reports them. The `status_code` policy reads the span status only. It never looks at `http.response.status_code` or `rpc.grpc.status_code`. Most HTTP and gRPC instrumentation sets the span status to Error for server errors, but if yours doesn't, add a policy on the attribute instead:

```yaml
      - name: http-5xx
        type: numeric_attribute
        numeric_attribute:
          key: http.response.status_code
          min_value: 500
          max_value: 599
```

## Your Collector Now Samples on Evidence, Not Chance

Your Collector now decides what to keep based on what happened in a trace, not a coin flip at the start. Errors stay. Slow traces stay. Health-check noise is nearly gone. And the baseline still gives you enough ordinary traffic for capacity planning and trends.

The storage bill goes down. The diagnostic signal goes up. Both at once.

For the thinking behind why this matters, [Your Sampling Strategy Is Lying to You](/articles/sampling-strategy/) makes the full argument. One exception to all of this: audit events should never pass through a tail sampler at all. [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) explains why they need a pipeline of their own.
