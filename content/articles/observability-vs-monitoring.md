---
title: "Observability vs. Monitoring: Why the Distinction Matters"
date: 2026-06-07
draft: false
excerpt: "Monitoring tells you when something you predicted goes wrong. Observability lets you work out what's happening when it's something you didn't. You need both, and the gap between them is where incidents drag on."
readtime: 6
tags: ["Observability", "Monitoring", "Philosophy", "Cost"]
card:
  title: "Observability vs. Monitoring"
---

People use the two words interchangeably. They aren't the same thing, and the difference isn't semantic. It decides which questions you can answer when something breaks at 2am.

## Two Different Questions

**Monitoring** is watching for failures you already know about. You decide in advance what matters (CPU, error rate, latency, queue depth), pick a threshold for each, and alert when one crosses the line. Monitoring answers one question: *is the thing I'm watching within acceptable bounds?*

**Observability** is a property of the system, not a tool you buy. The term is borrowed from control theory, where a system is observable if you can work out its internal state from its outputs alone. In software that means you can ask questions you never thought to ask before the incident, and answer them from the telemetry the system already emits. Observability answers a different question: *what is happening in there right now, and why?*

Monitoring needs you to know in advance what can go wrong. Observability doesn't.

## What Monitoring Structurally Can't See

Monitoring isn't broken. Every alert can be well tuned and still miss things, because of how the model is built. Two blind spots matter most.

**Cardinality blindness.** An error-rate alert tells you 2% of requests are failing. It can't tell you whether that 2% is spread evenly across your users or comes entirely from one tenant, one region, or one endpoint. Monitoring aggregates by design: you pre-compute a number so it stays cheap to store and fast to alert on. The aggregation is exactly what hides the structure that would tell you where to look. "2% errors" and "100% of requests from the Frankfurt enterprise tenant are failing" can be the same line on the same graph.

You can't fix this by adding a label for every dimension. Put `user_id` on a metric and you get one series per user, which is how metric bills explode. That's why [log-based monitoring](/guides/log-based-monitoring/) and good alert design both say the same thing: aggregate on bounded dimensions, then follow the alert into high-cardinality data to find the culprit. Monitoring tells you something's wrong. You need something else to find out who it's wrong for.

**Novel failure modes.** The alerts you write protect you from failures you've already seen. The first time something new shows up (a new dependency, a new traffic pattern, a config change that interacts badly with another one) there's no alert for it, because nobody knew to write one. The system looks green until users tell you otherwise. We've told that story in full in [The dashboard was green, but the request was broken](/articles/distributed-tracing-dashboard-was-green/): checkout failing for one narrow slice of carts while every metric looked healthy.

There's a slower version of the same blindness, too. A degradation can creep in under every static threshold until it finally snaps, which is the memory-leak scenario in [Observability 1.0 meant forensics](/articles/what-is-observability-2-and-why-scryops/). Different shape, same root cause: the threshold only knows the question it was written for.

## Where Monitoring Still Belongs

None of this makes monitoring obsolete. It's the right tool for known failure modes with clear operational thresholds. A disk at 90% should page someone. A TLS certificate that expires in under 30 days should raise a ticket. These are binary checks on well-understood conditions, and a threshold is the cheapest, most reliable way to catch them. You don't need to explore a full disk. You need to know about it before it fills.

The mistake is treating that layer as the whole job. Known failure modes are a subset of what can go wrong, and the subset shrinks as your system grows more services, more dependencies and more ways for them to interact. Monitoring is the floor. Observability is the ceiling. You need the floor or you fall through it. You need the ceiling or you hit your head on every incident you didn't predict.

Keep the alerts. Just make sure each one comes with a next step, which is the argument in [An Alert Without a Next Step Is Just Noise](/articles/alert-design-principles/). And don't let them multiply until nobody reads them, which is how you end up with [alert fatigue](/articles/alert-fatigue-is-an-observability-problem/).

## Five Things an Observable System Needs

"Observable" isn't a product you can buy, and you can't get there with one tool. A system you can actually ask new questions of needs five things.

**1. Comprehensive instrumentation.** Every service emits telemetry for every operation that matters, all the time, not just when something fails. If a service only logs errors, you can't tell "no requests" apart from "every request succeeded" or "every request got dropped before it arrived."

**2. Consistent naming.** If one service calls it `user_id`, another `userId` and a third `customerId`, no query can span all three. A shared vocabulary is what makes cross-service analysis possible. Without it, each team's telemetry can only be queried by that team. [Structured logging](/guides/structured-logging-machine-readable/) covers which field names to settle on, and why five teams sharing one schema beats one team's perfect one.

**3. Context propagation.** As a request moves through your system, its identity has to travel with it. The trace ID from service A has to show up in service B's spans, service C's logs and the database call at the end. Drop it at one hop and the trace splits in two. You end up with islands of data you can't connect. [Context propagation](/guides/otel-context-propagation/) shows where it usually gets lost.

**4. Centralised collection.** Telemetry only helps when you can query it together. A collection layer that receives signals from every service, normalises them and routes them to storage is the plumbing behind every cross-service query.

**5. Flexible analysis.** Raw telemetry doesn't answer anything on its own. You need to filter on any attribute, group by any dimension, jump from a span to its logs, and ask questions nobody planned for when the code was instrumented. That's the step that turns data into understanding.

Most teams have a partial version of all five. Incidents drag on in the gaps between partial and complete.

## The Practical Test

The clearest way to tell a monitored system from an observable one: what happens during an incident you've never seen before?

In a monitored system, the on-call engineer checks the dashboards they have, doesn't find the answer, and escalates to whoever knows the code. The incident gets resolved from expertise, not evidence. If that person is on holiday, it takes longer.

In an observable system, the on-call engineer asks the telemetry a question nobody built a dashboard for. Something like "show me every request slower than 500ms in the last 30 minutes, grouped by downstream dependency". The answer is in the data, and they don't need to know the codebase to find it.

That second state is the point of instrumentation. Not just for the incidents you've already had. For any incident.

If you want the longer arc of how the industry got from grepping log files to here, [The Evolution of System Understanding](/articles/evolution-of-system-understanding/) traces it.

## The Bill

Observability isn't free, and the bill scales with exactly what makes it useful. Monitoring stores pre-aggregated metrics: a fixed set of series, decided in advance, that stays bounded however much traffic flows through it. Observability keeps raw events and traces at enough fidelity to answer questions you haven't asked yet. That volume grows with traffic *and* with cardinality: every new attribute you can slice by is another dimension you're paying to keep.

The chart below is schematic. It shows the shape of the problem, not measured numbers.

{{< obs-observability-cost >}}

When the bill arrives, the instinct is to collect less. That defeats the point: every bit of telemetry you drop is a question you can no longer answer. There are two better levers.

**Sample smarter, not flatter.** Keep every error and every slow request, and a small fraction of the healthy, boring traffic. A flat random rate throws away the rare requests you need at the same rate as the ones you'll never look at. [Your Sampling Strategy Is Lying to You](/articles/sampling-strategy/) makes that case for traces, and [High-Throughput Logging](/guides/high-throughput-log-pipelines/) does the same for logs at volume.

**Tier your retention.** Keep raw, high-cardinality data hot for as long as your investigations actually look back, and roll it up or move it to cheap cold storage after that. Size the hot tier from your own post-mortems, not from a vendor default. [Log-based monitoring](/guides/log-based-monitoring/) walks through the hot/cold split.

Observability is the ability to ask any question. Cost control is deciding which questions are worth keeping the data to answer. Monitoring is how you make sure the questions you already know about never need asking twice.
