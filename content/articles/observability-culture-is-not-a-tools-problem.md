---
title: "You Don't Have an Observability Problem. You Have a Culture Problem."
date: 2026-06-10
draft: true
excerpt: "The Grafana dashboard exists. The traces are flowing. And yet nobody looks at them until something breaks. Tooling was never the bottleneck. Culture was."
readtime: 6
tags: ["Observability", "Philosophy", "Reliability", "On-Call"]
---

The Grafana dashboard exists. Traces are flowing. Logs are structured. The OTel Collector is running in production. And yet, when an incident fires, the first thing the on-call engineer does is open Slack and ask someone who knows the code.

The tooling was never the bottleneck. The habits were.

## The Tool-First Fallacy

Most organisations approach observability as a procurement problem. Pick the right platform, deploy it, and observability follows. This is backwards.

Observability is a mindset, a philosophy, and a practice that makes engineers better troubleshooters and better partners to the business. The tools are an expression of that mindset, not the source of it.

A team that has cultivated the right habits — instrumenting before shipping, reviewing error budgets weekly, treating on-call feedback as a product signal — will get value from a modest tooling stack. A team that hasn't will struggle with any platform you throw at it.

## The Blameless Culture Prerequisite

Observability requires engineers to make the system's failures visible. That only happens if the culture is safe enough to do so.

In a blame-heavy culture, engineers instrument conservatively. They do not add spans that expose slow code paths. They do not log context that could be used as evidence in a post-incident autopsy. They set alert thresholds high to avoid being paged for problems that might reflect on them.

In a blameless culture, engineers want to understand failures. They add instrumentation that makes the next incident easier to diagnose. They set alert thresholds calibrated to user impact, not self-protection.

Psychological safety is not a soft prerequisite. It is a hard one.

## Three Team Models

How observability teams are structured shapes adoption:

**Centralised:** A dedicated platform team owns the observability stack and sets standards. Fast to standardise, slow to respond to service-specific needs. Works well for organisations where the platform team has credibility and service teams trust its judgment.

**Federated:** Each service team owns its own observability. Fast to adapt, slow to standardise. Works well for mature engineering organisations with strong engineers who self-police.

**Hybrid (recommended):** A small platform team sets standards and owns the pipeline infrastructure. Service teams own their own instrumentation within those standards. The platform team is a product team with internal customers — it earns its authority through usefulness, not mandate.

The worst structure is a centralised team that mandates standards without providing the tooling to meet them.

## Making Observability Part of the Definition of Done

The most durable culture change is making observability a shipping requirement, not an afterthought. In practice:

**In the design doc:** Every new service or significant feature should answer: *what signals will tell us this is working correctly? What does failure look like in the telemetry?*

**In code review:** One checklist item: does this change add or remove instrumentation that affects our ability to observe the system?

**In the deployment checklist:** Before promoting to production, verify that the service emits the expected signals to the expected dashboards.

**In the incident review:** After every incident, explicitly answer: did we have the telemetry to detect this earlier? If not, what would we add?

## On-Call as a Feedback Loop

On-call is expensive and unpleasant by design — it forces the cost of poor observability back onto the team that produced it. That feedback loop is valuable if the team uses it.

The question after every page is not just "how do we fix this?" but "what would we need to have caught this earlier?" The answer goes directly into a ticket for the next sprint.

Teams that treat on-call as a punishment to be endured get nothing from it. Teams that treat it as a product feedback loop get progressively easier rotations.

## Concrete Patterns That Work

**Observability office hours:** A weekly slot where the platform team is available for questions. This is more effective than documentation because it creates a low-friction path to getting help and normalises asking.

**Error budget reviews:** A regular (weekly or monthly) review of SLO burn rates with the service team. Keeps error budget visible and creates accountability without blame.

**Observability champions:** One engineer per team whose role includes reviewing instrumentation quality, attending platform team planning, and sharing knowledge back. This is the single highest-leverage culture investment.

**Contribution model for standards:** Observability standards should be a community product, not a platform team decree. Engineering teams propose changes through a lightweight process. The platform team reviews for consistency. This creates ownership and buy-in that top-down mandates cannot.

The goal is not a perfect dashboard. The goal is a culture where every engineer, when they ship a change, knows what signal they would look for if it broke — and has already instrumented it.

For the people/process dimension of this in more depth, see [Observability Maturity Model](/guides/observability-maturity-model/). For what the on-call feedback loop looks like when it's broken, see [Alert Fatigue Is an Observability Problem](/articles/alert-fatigue-is-an-observability-problem/).

<!-- TODO: Add section on measuring culture change (observability adoption metrics, on-call load trend) -->
<!-- TODO: Add section on the community of practice model: guilds, working groups, Slack channels -->
