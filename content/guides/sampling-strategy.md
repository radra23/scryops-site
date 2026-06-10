---
title: "Your Sampling Strategy Is Lying to You"
date: 2026-05-26
draft: false
excerpt: "A flat 5% sampling rate sounds like a reasonable compromise between cost and coverage. It isn't. Head-based sampling doesn't give you a representative sample — it gives you a random one. Those are different things."
readtime: 7
tags: ["Tracing", "Sampling", "OpenTelemetry", "Observability"]
---

> "Sampling is not about seeing less. It's about seeing what matters — and knowing the difference."
> — A Staff Engineer, Reviewing the Observability Invoice

Head-based sampling makes the keep-or-discard decision at the moment the trace starts — before any outcome is known. A 5% sampling rate chosen at random is not a representative sample of what your system does. It's a random one. Those are different things, and the difference matters when the 5% you kept happens to exclude the one slow request that explains your latency spike.

A flat 5% sampling rate sounds like a reasonable compromise between cost and coverage. It isn't. Head-based sampling makes the keep-or-discard decision at the moment the trace starts, before a single span has been recorded. Before you know whether the request will succeed or fail. Before you know if it will take 20ms or 20 seconds. Before you know whether it belongs to a premium customer or a health check bot. You're sampling at random, and then telling yourself the result is representative.

When 95% of your requests succeed quickly and 5% fail slowly, a random 5% sample is mostly fast successes. The slow failures are as statistically likely to be dropped as anything else. You've optimised for cost and accidentally optimised against visibility into the requests that matter.

## The Decision You Make Before You Know What You're Deciding

The appeal of head-based sampling is genuine: make one decision per trace at the ingress point, propagate the sampling flag downstream via trace context, and all child spans follow the same decision. No buffering. No coordination. Minimal overhead. It's elegant — and it's wrong.

The problem is that the information you need to make an intelligent sampling decision doesn't exist yet at the point you're forced to make it.

{{< mermaid >}}
flowchart LR
    A[Request Arrives] --> B{Sample?}
    B -->|5% keep| C[Trace Recorded]
    B -->|95% drop| D[Trace Discarded]
    C --> E[Request Completes]
    D --> F[Request Completes]
    E --> G{Was it interesting?}
    F --> H{Was it interesting?}
    G -->|Yes — lucky| I[Visible]
    G -->|No| J[Noise you kept]
    H -->|Yes — unlucky| K[Gone forever]
    H -->|No| L[Noise you dropped]
{{< /mermaid >}}

You end up keeping a roughly equal proportion of boring fast requests and interesting slow ones. The 5% that survives is a random slice, not a curated one.

{{< insight lightbulb >}}
**The fundamental confusion:** Head-based sampling mistakes *random* for *representative*. A random 5% sample tells you how your system behaves on average. Tail-based sampling tells you when it's doing something worth investigating. These are different questions. For debugging, only one of them matters.
{{< /insight >}}

## Flipping the Decision Around

Tail-based sampling inverts the moment of judgement. Instead of deciding at trace start, you buffer span data as it arrives and make the keep-or-discard decision only after the full trace is complete — when you have the outcome in hand.

Now you can act on facts: did this trace contain any error spans? Did the end-to-end latency exceed your SLO threshold? Did it involve a high-value customer? Was it a deployment canary request? You can keep 100% of the things that matter and 1% of the things that don't.

{{< mermaid >}}
flowchart TD
    A[Spans Arrive] --> B[Collector Buffer]
    B --> C{Trace Complete?}
    C -->|No| B
    C -->|Yes| D{Evaluation}
    D -->|Error spans present| E[Keep — 100%]
    D -->|Latency > SLO threshold| E
    D -->|High-value customer| E
    D -->|Health check / noise| F[Sample — 1%]
    D -->|Normal fast request| G[Sample — 5%]
    E --> H[Export to Backend]
    F --> H
    G --> H
{{< /mermaid >}}

The tradeoff is real. Tail-based sampling requires buffering full traces in memory before the decision is made. For high-volume systems, that buffer needs careful sizing. And the OTel Collector doing the sampling needs to receive *all* spans for a given trace — which means consistent routing by trace ID, not random load balancing across Collector instances. These are solvable problems. The Collector's tail sampling processor is stable and production-grade, and the `loadbalancingexporter` handles trace-ID affinity across Collector instances cleanly.

## What It Looks Like in Production

The tail sampling processor lives in the Collector pipeline between receivers and exporters. A production-ready configuration that captures what matters and discards what doesn't:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s          # how long to buffer before deciding
    num_traces: 50000           # max traces held in memory
    expected_new_traces_per_sec: 1000
    policies:
      # Always keep error traces — these are your crime scenes
      - name: error-traces
        type: status_code
        status_code: {status_codes: [ERROR]}

      # Always keep slow traces (alert threshold: 1s)
      - name: slow-traces
        type: latency
        latency: {threshold_ms: 1000}

      # Always keep high-value customer traces
      - name: premium-customers
        type: string_attribute
        string_attribute:
          key: customer.tier
          values: [premium, enterprise]
          enabled_regex_matching: false

      # Keep just 1% of health check noise
      - name: health-checks
        type: and
        and:
          and_sub_policy:
            - name: is-health-check
              type: string_attribute
              string_attribute:
                key: http.route
                values: [/health, /ready, /metrics]
            - name: rate-limit
              type: probabilistic
              probabilistic: {sampling_percentage: 1}

      # 5% baseline on everything else
      - name: baseline
        type: probabilistic
        probabilistic: {sampling_percentage: 5}

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [tail_sampling]
      exporters: [otlp/backend]
```

The `decision_wait` of 10 seconds covers the vast majority of request lifetimes. For systems with genuinely long-running operations — async jobs, multi-step workflows — you can increase this, but you'll need to size the `num_traces` buffer accordingly.

## When the Old Approach Still Wins

Tail-based sampling isn't the answer in every situation. There are cases where head-based is the right choice, and it's worth knowing them.

**Very high-volume, low-latency systems** where buffering 50,000 traces per Collector instance isn't viable. At 100k RPS, you need either very large Collectors or a fundamentally different strategy.

**Systems where all requests are genuinely equivalent** — if every transaction matters equally and error rates are very low, random sampling really is representative.

**When you own the client** and can make intelligent decisions at the SDK level based on business context that isn't available in the Collector — for example, if your application knows a request is high-value before any spans are created.

{{< insight bookmark >}}
For most production services, the right answer is a **hybrid**: head-based sampling at 100% for errors and high-value operations (propagated as a sampling flag in trace context), combined with tail-based sampling at the Collector for everything else. You get the simplicity of head-based for known-important requests and the intelligence of tail-based for everything else.
{{< /insight >}}

## The Real Cost Argument

Teams often reach for flat 5% sampling purely for cost reasons. The maths feels clean: 5% of traces, 5% of the storage bill. But that logic breaks down when you consider what you're actually paying for.

In practice, errors and slow requests are a tiny fraction of overall traffic on a healthy system — often under 1%. Sampling 100% of errors and 5% of everything else doesn't cost meaningfully more than 5% across the board. And errors are the traces with the highest diagnostic value; every pound or dollar spent storing them is worth more than one spent on a random slice of successful health checks.

The real cost optimisation isn't a lower sampling rate — it's a smarter one. Drop 99% of `/health` checks. Keep 100% of checkout failures. Your bill goes down. Your signal goes up.

## Your Next Step

If you're running the OTel Collector and your current strategy is flat probabilistic sampling, the migration is straightforward: add the tail sampling processor with at minimum two policies — always-sample errors, probabilistic-5% everything else. Route traces through a single Collector instance or use the `loadbalancingexporter` for trace-ID affinity across multiple Collector instances. Watch the Collector's memory usage for the first 48 hours.

You won't get perfect coverage. Some interesting traces will still fall through the cracks — the tail sampler can only evaluate what it has buffered when `decision_wait` expires. But you'll stop systematically discarding the evidence you need most.

That's a trade worth making.

{{< obs-mascot class="rogue" quip="I dropped 99% of the traces in the night. Kept the errors and the slow ones. ...probably fine. I did not write down what I dropped, which is, ironically, the whole problem." >}}
