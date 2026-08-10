---
title: "SLOs and Error Budgets"
date: 2026-06-11
draft: true
excerpt: "Service Level Objectives and error budgets give reliability a quantitative shape — a target, a budget for deviation, and burn rate signals that tell you when to stop shipping and start fixing."
readtime: 6
tags: ["SLOs", "Alerting", "Reliability", "Observability", "On-Call"]
---

Service Level Objectives (SLOs) translate reliability from a vague aspiration into a number you can measure, alert on, and make engineering decisions against. The error budget — the allowed amount of unreliability — is what makes the number actionable: it turns a compliance question ("are we meeting the SLO?") into a spend question ("how fast are we spending the budget, and does that change what we ship next?").

## Core Definitions

**Service Level Indicator (SLI)** — a quantitative measurement of a service behaviour that reflects the user experience. Common SLIs: request success rate, request latency at a given percentile, data freshness lag, throughput.

**Service Level Objective (SLO)** — a target level of reliability expressed as a percentage over a rolling time window. Examples: "99.9% of requests complete in under 200ms over 30 days"; "99.95% of API calls return successfully over 28 days."

**Error Budget** — the inverse of the SLO. A 99.9% SLO means 0.1% of requests may fail — that 0.1% is the error budget. When the budget runs out, the team cannot absorb more risk until it resets.

**Burn Rate** — the rate at which the error budget is being consumed relative to the pace that would exhaust it exactly at the end of the window. A burn rate of 1× means you'll exhaust the budget in exactly 30 days. A burn rate of 14.4× means you'll exhaust it in about 2.1 days.

{{< mermaid >}}
graph LR
    A[SLI] -->|measured against| B[SLO target]
    B -->|defines| C[Error Budget]
    C -->|monitored via| D[Burn Rate]
    D -->|triggers| E[Alerts and actions]
{{< /mermaid >}}

## Error Budget Calculation

For a 99.9% SLO over a 30-day window:

- Error budget = 100% − 99.9% = 0.1%
- Allowed downtime = 0.001 × 30 days × 24 hr × 60 min = **43.2 minutes**

For a 99.95% SLO over 28 days:

- Error budget = 0.05%
- Allowed downtime = 0.0005 × 28 × 24 × 60 = **20.2 minutes**

{{< mermaid >}}
graph TD
    A[30-day window] --> B[99.9% uptime target]
    A --> C[0.1% error budget]
    B --> D[43,157 minutes available]
    C --> E[43.2 minutes allowed downtime]
{{< /mermaid >}}

The budget is not a ceiling for incidents — it is a risk allocation. Planned changes, deployments, experiments, and maintenance all draw from the same budget as unplanned failures. A team with budget remaining can move fast; a team at budget must stop and stabilise.

## Burn Rate Alerts

A single threshold alert on the SLO catches incidents too slowly. By the time you've failed enough to violate a 30-day SLO target, you've already had a significant outage. Multi-window, multi-burn-rate alerting detects incidents at different severities while they can still be contained.

Standard thresholds for a 30-day SLO (from Google SRE):

| Burn Rate | Window | Budget Consumed | Action |
|---|---|---|---|
| 14.4× | 1 hour | 2% | Page immediately |
| 6× | 6 hours | 5% | Page |
| 2× | 3 days | 20% | Create ticket |

At 14.4× burn, the budget exhausts in 30 ÷ 14.4 ≈ 2.1 days. The 1-hour window is short enough to catch fast-moving incidents early; the 6-hour window catches sustained moderate burns that the 1-hour window misses.

{{< obs-burn-rate-triage >}}

{{< insight >}}
At 14.4× burn rate, you exhaust a 30-day budget in ~51 hours — not 2 hours. The common misreading of burn rate is treating the multiplier as a time divisor applied to the window length. The correct formula is: days to exhaustion = window_days ÷ burn_rate.
{{< /insight >}}

## Defining Good SLIs

An SLI that doesn't reflect user experience produces an SLO that doesn't protect users. Good SLIs share four properties:

{{< mermaid >}}
graph LR
    A[Good SLI] --> B[User-focused]
    A --> C[Controllable]
    A --> D[Measurable]
    A --> E[Meaningful]
    B --> F[Reflects user experience]
    C --> G[Your team can affect it]
    D --> H[Consistently collectable]
    E --> I[Correlated with business outcomes]
{{< /mermaid >}}

Prefer SLIs measured at the edge of the system (from the user's perspective) over internal measurements. A p99 latency measured at the load balancer is a better SLI than p99 measured at a single microservice — it captures the whole user experience, including infrastructure above and below your code.

**Time windows:** 28–30 days for most services (aligns with billing cycles, long enough to absorb weekday/weekend variance). 7 days for services with very high change rates where a 30-day window obscures recent trends.

## Setting SLO Targets

Set initial targets from observed performance, not aspirational performance:

{{< mermaid >}}
graph LR
    A[Measure current performance] --> B[Set target below current level]
    B --> C[Monitor 2-3 months]
    C --> D[Gather user feedback]
    D --> E[Adjust target]
    E --> F[Review quarterly]
{{< /mermaid >}}

Setting the initial SLO below current performance gives you a buffer while you learn the service's baseline. An SLO set at exactly current p99 latency will fire alerts immediately on any regression. Start conservative; tighten as you understand the service's normal variation.

## Error Budget Policy

The error budget only works as a decision-making tool if the policy around it is written down and enforced. Three areas need explicit policy:

{{< mermaid >}}
graph TD
    A[Error Budget Policy] --> B[Consumption rules]
    A --> C[Reset policy]
    A --> D[Response actions]
    B --> B1[What counts as a burn?]
    B --> B2[How is impact measured?]
    C --> C1[Reset interval]
    C --> C2[Overrun handling]
    D --> D1[Alert thresholds]
    D --> D2[Required actions per threshold]
{{< /mermaid >}}

**Consumption rules** define what draws from the budget: unplanned outages, degraded performance events, and — critically — planned changes that cause errors. A deployment that causes a 10-minute error spike draws from the same budget as an unplanned incident.

**Reset policy** defines what happens when the budget runs out. The standard response is a feature freeze: no new deployments until the budget resets or until the team has made targeted reliability improvements. Define this in advance, not during an incident.

**Response thresholds** should match the burn rate alert tiers: at 50% budget consumed, increased review; at 75%, no non-critical deployments; at 100%, feature freeze. These thresholds need to be agreed across engineering and product before they're ever invoked.

## Integration with Business Processes

{{< mermaid >}}
graph TD
    A[SLO / Error Budget] --> B[Change management]
    A --> C[Capacity planning]
    A --> D[Product decisions]
    B --> B1[Deploy go/no-go]
    B --> B2[Maintenance windows]
    C --> C1[Growth projections]
    C --> C2[Infrastructure investment]
    D --> D1[Feature vs. reliability priority]
    D --> D2[Technical debt timing]
{{< /mermaid >}}

**Change management** — the error budget is the input to deploy decisions. A team with a full budget can move fast; a team at 10% remaining needs to treat each deployment as a risk event. Build error budget remaining into your deploy checklist.

**Capacity planning** — SLO burn patterns reveal growth pressure. A service whose burn rate trends upward across multiple windows without a corresponding incident is approaching a capacity ceiling. Error budget data feeds infrastructure investment decisions before the ceiling is hit.

**Product decisions** — when the budget is exhausted, the conversation about whether to ship or fix should already be resolved by policy. The budget makes that conversation objective: not "how important is this feature?" but "do we have budget to absorb this risk?"

<!-- TODO: Add PromQL / recording rule examples for tracking SLO burn rate -->
<!-- TODO: Add Prometheus alerting rule examples for multi-window burn rate alerts -->
<!-- TODO: Add guidance on SLO measurement for non-HTTP services (queues, batch jobs, streaming pipelines) -->
<!-- TODO: Cover composite SLOs — services with multiple SLIs that each contribute to one error budget -->

- [Alert Design Principles](/guides/alert-design-principles/) — how burn rate alerts fit into a broader alerting strategy
- [Alert Correlation](/guides/alert-correlation/) — grouping burn rate alerts with upstream symptoms
- [On-Call Procedures](/guides/on-call-procedures/) — how error budget status affects incident response and handoffs
