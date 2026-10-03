---
title: "Your Sampling Strategy Is Lying to You"
date: 2026-09-29
draft: false
aliases: ["/guides/sampling-strategy/"]
excerpt: "A flat 5% sampling rate sounds like a sensible trade between cost and coverage. It isn't. A random slice of your traffic is mostly the requests you'll never look at, and it throws away the rare ones you need at the same rate."
readtime: 7
tags: ["Tracing", "Sampling", "OpenTelemetry", "Observability"]
---

A flat 5% sampling rate sounds like a sensible trade between cost and coverage. It isn't. Head-based sampling decides whether to keep a trace the moment it starts, before a single span has been recorded. Before you know whether the request will succeed or fail. Before you know if it'll take 20ms or 20 seconds. Before you know whether it came from a premium customer or a health-check bot.

The sample you get is perfectly fair. That's the problem. When 99% of your requests are fast successes and 1% fail slowly, a random 5% is 99% fast successes too, and the slow failures get dropped at exactly the same rate as everything else. For the one slow request that explains tonight's latency spike, 5% means a one-in-twenty chance it survived. You optimised for cost and quietly optimised against seeing the requests that matter.

## The Decision You Make Before You Know What You're Deciding

The appeal of head-based sampling is real. You make one decision per trace at the entry point, pass the sampling flag downstream in the trace context, and every child span follows it. No buffering. No coordination. Almost no overhead. It's elegant, and for debugging it's the wrong tool.

The information you need to make a good sampling decision doesn't exist yet at the moment you're forced to make it.

{{< mermaid >}}
flowchart TD
    A[Request Arrives] --> B{Sample?}
    B --->|5% keep| C[Trace Recorded]
    B --->|95% drop| D[Trace Discarded]
    C --> E[Request Completes]
    D --> F[Request Completes]
    E --> G{Was it interesting?}
    F --> H{Was it interesting?}
    G -->|Yes, lucky| I[Visible]
    G -->|No| J[Noise you kept]
    H -->|Yes, unlucky| K[Gone forever]
    H -->|No| L[Noise you dropped]
{{< /mermaid >}}

You keep boring fast requests and interesting slow ones in the same proportion. The 5% that survives is a random slice, not a curated one.

{{< insight lightbulb >}}
**Fair isn't the same as useful.** A random 5% sample tells you how your system behaves on average, and it's good at that. Tail-based sampling tells you when your system is doing something worth investigating. Those are different questions, and when you're debugging, only the second one matters.
{{< /insight >}}

## Flipping the Decision Around

Tail-based sampling moves the moment of judgement. Instead of deciding at the start, the Collector buffers spans as they arrive and decides later, once the outcome is in hand. It can't know for certain when a trace has finished, so it waits a fixed `decision_wait` after the trace's first span and decides then. Set that wait longer than your slowest normal request and you'll catch nearly all of it.

Now you can decide on facts. Did the trace contain an error? Did it blow through your latency threshold? Did it come from a high-value customer? Was it a canary request? You can keep all of the traces that matter and 1% of the ones that don't.

{{< mermaid >}}
flowchart TD
    A[Spans Arrive] --> B[Collector Buffer]
    B --> C{decision_wait elapsed?}
    C -->|No| B
    C -->|Yes| D{Evaluate every policy}
    D -->|Error span<br/>present| E[Keep: 100%]
    D -->|Latency<br/>over threshold| E
    D -->|High-value<br/>customer| E
    D -->|Health check| F[Sample: 1%]
    D -->|Everything<br/>else| G[Sample: 5%]
    E --> H[Export to Backend]
    F --> H
    G --> H
{{< /mermaid >}}

The trade-off is real. Tail sampling buffers traces in memory until the decision, and on a busy system that buffer needs careful sizing. And the Collector doing the sampling has to receive *every* span of a trace, which means routing by trace ID instead of spreading spans at random. Both are solvable. The Collector's `tail_sampling` processor is Beta for traces and widely run in production. At scale, you put a first tier of Collectors running the `loadbalancingexporter` in front of the sampling tier, and it keeps each trace together.

## What It Looks Like

The policies live in the Collector's `tail_sampling` processor. Here's the heart of a configuration that keeps what matters and drops what doesn't:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s          # wait this long after a trace's first span
    num_traces: 50000           # most traces held in memory at once
    expected_new_traces_per_sec: 1000
    policies:
      # Always keep error traces. These are your crime scenes.
      - name: error-traces
        type: status_code
        status_code: {status_codes: [ERROR]}

      # Always keep slow traces (threshold: 1s)
      - name: slow-traces
        type: latency
        latency: {threshold_ms: 1000}

      # Always keep high-value customer traces
      - name: premium-customers
        type: string_attribute
        string_attribute: {key: customer.tier, values: [premium, enterprise]}

      # Keep 1% of health checks
      - name: health-checks
        type: and
        and:
          and_sub_policy:
            - name: is-health-check
              type: string_attribute
              string_attribute: {key: http.route, values: [/health, /ready, /metrics]}
            - name: one-percent
              type: probabilistic
              probabilistic: {sampling_percentage: 1}

      # 5% of everything that isn't a health check
      - name: baseline
        type: and
        and:
          and_sub_policy:
            - name: not-health-check
              type: string_attribute
              string_attribute: {key: http.route, values: [/health, /ready, /metrics], invert_match: true}
            - name: five-percent
              type: probabilistic
              probabilistic: {sampling_percentage: 5}
```

That last policy is where most configs go wrong. The Collector keeps a trace if *any* policy says yes, and policy order changes nothing. A plain 5% `baseline` would keep 5% of health checks on its own, and the 1% rule above it would be decoration. When we ran the naive version through a real Collector, health checks came out at 4.7%. With `baseline` excluding them, they came out at about 1%, and failing health checks were still kept in full by the error policy.

The full setup, with receivers, a memory limiter, exporters and the scaling tier, is in [How to Configure OTel Collector Tail Sampling](/howtos/configure-collector-tail-sampling/).

## When the Old Approach Still Wins

Tail-based sampling isn't the answer everywhere. Head-based sampling is still the right call in a few situations.

**Very high-volume, low-latency systems** where buffering tens of thousands of traces per Collector isn't viable. At 100k requests per second, you need very large Collectors or a different strategy altogether.

**Systems where every request really is equivalent.** If each transaction matters equally and failures are vanishingly rare, a random sample tells you what you need.

**When the application knows before the Collector does.** If your code knows a request is high-value before any spans exist, it can make that call at the SDK level with business context the Collector will never see.

{{< insight bookmark >}}
**Head and tail sampling don't mix the way you'd hope.** A trace that head sampling drops is gone before the tail sampler ever sees it, and you can't head-sample "all the errors" because nobody knows about the error when the trace starts. So for most services, let the SDKs record everything (the default `ParentBased` sampler with every root sampled) and let the Collector's tail sampler choose. If volume forces you to head-sample, do it only on routes you already know are low-value, and send everything else through in full.
{{< /insight >}}

## The Real Cost Argument

Teams often reach for flat 5% sampling purely on cost. The maths feels clean: 5% of traces, 5% of the storage bill. That logic falls apart once you look at what you're paying for.

On a healthy system, errors and slow requests are usually a small fraction of traffic. Keeping all of them plus 5% of everything else doesn't cost much more than 5% across the board. And those are the traces with the most diagnostic value. Every pound or dollar spent storing them is worth more than one spent on a random slice of successful health checks.

One catch before you celebrate. If you work out request rates or error rates from your traces, tail sampling skews them on purpose, because errors are now over-represented. Compute those numbers from spans *before* the sampler runs, for example with the `spanmetrics` connector in a pipeline ahead of `tail_sampling`.

The real cost saving isn't a lower sampling rate. It's a smarter one. Drop 99% of `/health` checks. Keep every checkout failure. Your bill goes down. Your signal goes up.

## Your Next Step

If you run the OTel Collector and your current strategy is flat probabilistic sampling, the move is small: add the tail sampling processor with at least two policies, keep every error and sample the rest. Run a single Collector, or put a `loadbalancingexporter` tier in front for trace-ID affinity across several. Then watch the Collector's memory for the first 48 hours. [How to Configure OTel Collector Tail Sampling](/howtos/configure-collector-tail-sampling/) walks through it step by step.

You won't get perfect coverage. Spans that arrive after `decision_wait` miss the decision, so a few interesting traces will still slip through. But you'll stop systematically throwing away the evidence you need most.

That's a trade worth making.

{{< obs-mascot class="rogue" quip="I dropped 99% of the traces in the night. Kept the errors and the slow ones. ...probably fine. I did not write down what I dropped, which is, ironically, the whole problem." >}}
