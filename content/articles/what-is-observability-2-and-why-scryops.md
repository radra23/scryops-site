---
title: "Observability 1.0 lets us understand what happened. Observability 2.0 asks us to see what's coming."
date: 2026-03-15
draft: false
excerpt: "Observability 1.0 taught us to look backward. Observability 2.0 demands we look forward. Here's the argument for a shift most teams haven't made yet — and why I named this site after a medieval divination practice."
readtime: 6
tags: ["Observability", "OpenTelemetry", "AI", "Philosophy"]
---

## Most teams are still stuck in the old loop. There's a reason this site takes its name from a way of looking ahead, not behind.

The dashboards aren’t broken. The alerts aren’t broken. The problem is the model.

Observability — real observability — was never supposed to be a reactive practice. You don’t instrument your systems, so you're the last to know when something goes wrong. You do it so you’re never caught off guard.

But most teams didn’t build that. They made dashboards—lots of them. They wired PagerDuty up, added thresholds for p99 latency, and called it done. What they ended up with was accident reconstruction in great detail, three minutes after the fact, for whoever was unlucky enough to be on call.

That’s not observability. That’s forensics with a pretty UI.

## Observability 1.0: the model we inherited

The first observability stack was built out of necessity. Prometheus made metrics cheap. Loki made logs affordable. Jaeger made tracing accessible. OpenTelemetry gave us a shared language. I've shipped production systems on all of them. The tools aren't the problem. The model is.

The model that those tools enforce is fundamentally retrospective. Metric crosses threshold → alert fires → human investigates → human fixes. Every step is reactive. The human is always last in line.

{{< obs-reactive-loop >}}

Fast forward to 2026. You're running hundreds of microservices across clouds, pumping out millions of spans every second. The old reactive model can't keep up. It's slow and inefficient. Picture a memory leak nudging one service's latency higher, hour by hour. No alert fires until the threshold breaks. By then, the API will be timing out, and customers will already be feeling it. Engineers scramble across dashboards, always chasing the problem, never catching up. By the time you find the real root cause, the damage is done. That's the price of staying reactive.

{{< obs-memory-leak >}}

## Observability 2.0: a different question

Observability 2.0 isn’t about prettier dashboards. It isn’t about shaving 30% off your MTTD. It’s a different question entirely.

Instead of asking *”what happened?”* it asks *”what’s about to happen, and how do we stop it?”*

{{< obs-comparison-table >}}

Making that shift means building what the old model can’t deliver: a way to see connections, predict trouble, and act before users notice.

**Signal correlation at scale.** Not logs, metrics, and traces in their own corners, but one model that sees the connections. A spike in error rate alone is just a blip. But if it happens alongside a fresh deployment, a database pool that’s nearly full, and a downstream service with p95 latency creeping up for hours, that’s not noise. That’s a warning.

{{< obs-signal-correlation >}}

**Predictive inference.** ML models and LLMs that spot patterns *before* they turn into incidents. Not “this crossed a threshold.” More like: “This pattern has come before an outage eight out of the last ten times, and we’re three hours into it now.” Most teams are just starting to try these predictive approaches. A few big tech companies have ML-driven forecasting in production. For everyone else, it’s still experimental or just leaving the pilot phase. The promise is real. The tooling and practices are still catching up.

**Proactive remediation.** No more paging a human and waiting. The system rolls back a deployment, scales a service, or throttles traffic based on predicted risk, not confirmed failure. It acts on what it sees coming, not what has already happened.

The industry data makes the case for the shift plainly.

{{< obs-stats-chart >}}

This is what I mean by Observability 2.0. The work of actually building it—the tools, the patterns, the architecture—is what I call **scryops**.

## Why scryops

*Scrying* is a medieval divination practice. You stare into a reflective surface—a crystal ball, a mirror, a bowl of water—and try to see what’s coming instead of what already happened. That’s the analogy. Now we’ll leave it behind.

I picked the name deliberately. Not because I believe in magic. Because I believe in the aspiration.

The entire history of software operations has been about staring into the past. Log files. Post-mortems. “Let’s look at what the metrics were doing before the outage.” Scrying is the opposite of that: you look forward. You act on what you see before it arrives.

Scryops means bringing together every signal—telemetry, events, topology, deployment state, and history—to predict what your system will do and fix issues before users notice. Not sure where to start? Pick one service. Try an experiment. Bring logs, metrics, and traces for that service into one place where you can actually correlate them. Find a recurring incident and see if you can create even a simple rule or ML prediction that spots trouble before users feel it. The goal isn’t perfection. It’s about learning how to catch early signs and trigger a test fix. Start small. See what works. Keep improving. Every experiment makes the future a little less surprising.

That’s the goal. Not zero downtime as a lucky streak. Zero downtime as a practice.

## What this publication covers

I'm building scryops out in the open. No hype. No vendor whitepapers. I'll dig into original research, case studies, and pilot projects from teams actually trying predictive observability. Netflix has run ML pilots for early anomaly prediction. Shopify's SREs have linked deployment, telemetry, and topology data to spot incidents before users notice. Startups are building open-source tools to unify logs, metrics, and traces for predictive risk modeling. I'll share what these teams learned, what tripped them up, and how you can adapt their approaches. Expect articles on designing OTel pipelines for predictive models, what eBPF-based instrumentation unlocks at runtime, where LLMs help with anomaly detection (and where they don't), and the real trade-offs of acting before you've confirmed a fault.

If you’re trying to close the gap between “we have good observability” and “we knew about the problem before users did,” this is the place.

The crystal ball is just a metaphor. Signal correlation is real. Let’s build it.
