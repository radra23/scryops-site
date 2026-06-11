---
title: "Observability 1.0 meant forensics. Observability 2.0 means prevention."
date: 2026-03-15
draft: false
excerpt: "Observability 1.0 taught us to look backward. Observability 2.0 asks us to look forward. Most teams haven’t made that shift yet. That’s why I named this site after a medieval divination practice."
readtime: 6
tags: ["Observability", "OpenTelemetry", "AI", "Philosophy"]
---

## Most teams are caught in the same old loop

The dashboards aren’t broken. The alerts aren’t broken. The problem is the model.

Real observability was never meant to be reactive. You don’t add telemetry just to be the last to know when things break. You do it so you’re never surprised.

But that’s not what most teams built. They made dashboards. Lots of dashboards. PagerDuty wired up, p99 latency thresholds set, job done. What they really built was accident reconstruction in high definition, three minutes too late, for whoever drew the short straw on call.

That’s not observability. That’s forensics with a new paint job.

## Observability 1.0: the model we inherited

The first observability stack was built out of necessity. Prometheus made metrics cheap. Loki made logs affordable. Jaeger made tracing accessible. OpenTelemetry gave us a shared language. I’ve shipped production systems on all of them. The tools aren’t the problem. The model is.

The model those tools push always looks backward. A metric crosses a line, an alert fires, a human investigates, a human fixes. Every step is reactive. The human finds out last.

{{< obs-reactive-loop >}}

Fast forward to 2026. Hundreds of microservices, millions of spans every second, spread across clouds. The old reactive model can’t keep up. It’s slow. It wastes time and attention. A memory leak pushes one service’s latency higher, hour by hour. No alert fires until the threshold finally snaps. By then, the API is timing out and customers are already feeling it. Engineers scramble through dashboards, always chasing, never catching up. By the time you find the real cause, the damage is done. That’s the price of staying reactive.

{{< obs-memory-leak >}}

## Observability 2.0: a different question

Observability 2.0 isn’t about prettier dashboards. It isn’t about shaving seconds off incident response. It’s about asking a new question.

Instead of asking *”what happened?”* it asks *”what’s about to happen, and how do we stop it?”*

{{< obs-comparison-table >}}

Making that shift means building what the old model never could. You see the connections, spot trouble coming, and act before users notice.

**Signal correlation at scale.** Not logs, metrics, and traces each in their own silo. One model that sees the connections. A spike in error rate alone is just a blip. But if it lands with a fresh deployment, a database pool almost full, and a downstream service with p95 latency creeping up for hours, that’s not noise. That’s a warning.

{{< obs-signal-correlation >}}

**Predictive inference.** ML models and LLMs that spot patterns before they become incidents. Not just a threshold crossed. More like: this pattern showed up before an outage eight out of the last ten times, and we’re three hours into it now. Most teams are just starting to try these predictive approaches. A few big tech companies have ML-driven forecasting running in production. For everyone else, it’s still experimental or just leaving the pilot phase. The tooling hasn't caught up to the promise yet — which is exactly where practitioners should be paying attention.

**Proactive remediation.** No more paging a human and waiting. The system rolls back a deployment, scales a service, or throttles traffic based on predicted risk, not confirmed failure. It acts on what it sees coming, not what has already happened.

The industry data makes the case for this shift.

{{< obs-stats-chart >}}

This is what I mean by Observability 2.0. The work of actually building it—the tools, the patterns, the architecture—is what I call **scryops**.

## Why scryops

*Scrying* is a medieval divination practice. You stare into a reflective surface—a crystal ball, a mirror, a bowl of water—and try to see what’s coming instead of what already happened. That’s the analogy. Now we’ll leave it behind.

I picked the name on purpose. Not because I believe in magic. Because I believe in the goal: seeing what’s coming, not just what already happened.

Software operations has always looked backward. Log files. Post-mortems. Let’s check what the metrics were doing before the outage. Scrying flips that. You look forward. You act on what you see before it arrives.

Scryops means bringing together every signal — telemetry, events, topology, deployment state, history — and using that picture to predict what your system will do before users notice. Usually, you start with one service and one recurring incident. Pull the signals together, find the pattern that comes before the problem, and build even a simple rule that catches it early. That first experiment is where the model stops being abstract.

That’s the goal. Not zero downtime as a lucky streak. Zero downtime as a practice.

## The gap this publication closes

I'm building scryops out in the open. No hype. No vendor whitepapers. I'll dig into original research, case studies, and pilot projects from teams actually trying predictive observability. Teams at Netflix and Shopify have published engineering work on this: ML-based anomaly detection in time-series infrastructure, linking deployment state and topology data to get ahead of incidents. Startups are building open-source tools to unify logs, metrics, and traces for predictive risk modeling. I’ll share what these teams learned, what tripped them up, and how you can adapt their approaches.

Expect articles on designing OTel pipelines for predictive models, what eBPF-based instrumentation unlocks at runtime, where LLMs help with anomaly detection and where they fall short, and the real trade-offs of acting before you have confirmed a fault.

If you’re trying to close the gap between “we have good observability” and “we knew about the problem before users did,” that gap is what this publication is for.

The crystal ball is just a metaphor. Signal correlation is real.

{{< insight bookmark >}}
**Where to start.**
Pick one service with a known recurring incident. Pull its telemetry for the 30 minutes before each occurrence — spans, error rates, upstream and downstream latency. Look for the signal that precedes the problem. Build even a simple rule that fires on it early. That first experiment is where the model stops being abstract.
{{< /insight >}}

{{< obs-mascot class="oracle" quip="I gazed into the orb and beheld it: checkout falls at 14:02. It is 14:01. I have known for six weeks — the signal was right there in the spans, plain as day. I filed the ticket. No one read the ticket. The orb foresaw that too." caption="The Oracle is Observability 2.0 given a body: the outage was always visible in the signals — someone just had to look before it happened." >}}
