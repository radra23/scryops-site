---
title: "Logs, Metrics, Traces — and the Signal Nobody Added to That List"
date: 2026-06-16
draft: true
excerpt: "Logs tell you that something broke. Metrics tell you how often. Traces tell you which path the request took. None of them tell you which line of code did it. That's the gap continuous profiling fills — and it's been quietly filling it in production at companies you've heard of for years."
readtime: 6
tags: ["Profiling", "Observability", "Monitoring"]
---

<!--
ARTICLE: The editorial case for continuous profiling as the fourth pillar of
observability. This is the "why should I care" piece. Tone is tech-storyteller
— narrative, warm, the problem should be felt before the solution is named.

TARGET READER: An engineer who knows logs/metrics/traces well and has probably
done ad-hoc profiling on their laptop, but has never run a profiler in
production continuously. They're skeptical: "won't that hurt performance?"

THESIS: The three traditional signals all describe the system from the outside.
Profiling is the only signal that describes what the code is doing internally —
which function, which line, how much of the CPU second it consumed. It doesn't
replace logs/metrics/traces; it answers the question they can't.

STRUCTURE:

## The Question Nobody's Signals Could Answer
Open with the scenario from the source material: a Node.js service is quietly
burning CPU in production. Latency p99 is elevated. Error rate is fine. The
traces show the requests are slow but the span tree doesn't tell you why —
the time is being consumed somewhere inside a single span that isn't broken
down further. You could add more spans. You could add logging. But you don't
know WHERE to add them. That's the problem continuous profiling solves.

## What a Profile Actually Measures
Explain sampling-based profiling without jargon:
- A profiler interrupts the running program ~100 times per second
- At each interrupt it records the current call stack (who called whom)
- After many samples, the aggregate shows which functions appear most often
- Frequency ≈ time spent — a function that appears in 40% of samples consumed
  roughly 40% of CPU time

This is different from tracing, which follows a specific request. Profiling
doesn't care about requests — it watches the CPU and asks "what is it doing
right now?" repeatedly.

## The Flame Graph — Reading the Story of a CPU Second
The flame graph section from the source material is excellent; adapt it to
the site's voice.

Key point to nail: a flame graph is NOT a timeline. Width = share of CPU time.
Vertical = call hierarchy (parent at top, children below). The widest LEAF box
is the culprit — a function consuming CPU with nothing below it. A wide box
that is wide only because its children are wide is just a busy parent.

Analogy idea: reading a flame graph is like reading a budget breakdown.
The total at the top is 100% of CPU time. Each layer shows where it went.
Find the leaf that's eating the budget.

Consider a Mermaid diagram showing a simplified flame graph structure
(can't do the real SVG flame graph, but can show the hierarchy concept).

## Continuous vs. On-Demand — Why "Always On" Changes What You Can Debug
Traditional profiling: you notice a problem, you attach a profiler, you
reproduce the issue, you analyse it. This works in development. In production
it fails: you can't reproduce the exact conditions, the problem may be gone
by the time you've set up the profiler, and the act of attaching may change
the behaviour.

Continuous profiling inverts this: the profiler is always running at low
overhead, storing a rolling window of profile data. When the CPU spike happens
at 3 PM on a Tuesday, you don't reproduce — you scroll back to 3 PM and look.

"By the time the on-call alert fires, you already have the evidence."

## The Overhead Question (The Honest Answer)
Address the skepticism directly. Key numbers:
- Sampling at ~100Hz is non-intrusive by design — the CPU cost of the interrupt
  is tiny
- Memory: Grafana Labs reports typically under 50 MB per process for all profile
  types, confirmed in the source project's own testing
- Profiles are buffered and shipped on a configurable interval (default 60
  seconds) — the network cost is minimal

The profiler is also designed to be non-fatal: if the backend is down or
slow, the SDK drops new profiles rather than ballooning memory or crashing
the application.

Practical advice: test your own workload before making blanket claims, but
don't let overhead anxiety stop you from trying it. The cost is almost
always smaller than expected.

## The Profile Types — Three Lenses on the Same Application
Adapt the profile types table from the source material:
- CPU: where the processor is spending cycles (hot loops, CPU exhaustion)
- Wall: where real elapsed time goes, including I/O wait (slow endpoints,
  blocking operations)
- Heap: where memory is being allocated (growth, leaks)

Practitioner instinct:
- Start with Wall for "why is this slow" — it captures both CPU and waiting
- Switch to Heap when memory is the suspect
- Reach for CPU when the box is pegged at 100%

## Close: The Signal That Arrives Last
The closing should acknowledge that profiling is typically the last signal
teams add — after logs, metrics, and traces are in place. That ordering is
fine; each signal is useful independently. But the pattern is consistent:
once teams add profiling, they tend to find bugs they didn't know they had.
Not because the other signals missed something — because profiling answers
a question the other signals literally cannot.

"The question isn't whether your code has inefficient functions. It does.
The question is whether you know which ones."

VOICE NOTES:
- Keep the "three pillars" framing — logs/metrics/traces — and position
  profiling as additive, not a replacement. Don't trash the other signals.
- The skeptical reader needs to trust the overhead numbers. Cite Grafana Labs'
  own fleet numbers (from the source material) and frame them honestly as
  "from Grafana Labs' own reporting, confirmed in our testing."
- Don't mention Pyroscope specifically until very late or not at all — this
  article is about the concept, not the implementation. The guide covers
  the implementation.

CROSS-LINK TO:
- Guide: content/guides/pyroscope-nodejs-aws-setup.md
  "Ready to instrument? The guide covers a full Pyroscope + Node.js deployment
  on AWS, from VPC to flame graph."
- How-to: content/howtos/pyroscope-deployment-war-stories.md
  Reference from the guide, not necessarily from this article directly.
-->
