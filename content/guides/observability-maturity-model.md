---
title: "The Observability Maturity Model"
date: 2026-06-10
draft: true
excerpt: "Not every team needs the same observability stack. A maturity model that maps your current state — from reactive log grepping to proactive reliability engineering — and gives you a concrete next step, not a shopping list."
readtime: 9
tags: ["Observability", "Reliability", "Philosophy", "Best Practices"]
---

Observability is not a destination, but a continuous journey of improvement. The question is not whether to have observability, but where you are on the path and what the next concrete step looks like.

Most organisations buy tools before they understand what maturity stage they are at. A team at Level 1 purchasing a Level 4 platform does not jump to Level 4. It accumulates expensive tooling it cannot use.

## The Four Pillars at Every Level

Before the levels, a framework. A complete observability program is built on four pillars — and maturity advances when all four advance together, not just the technology:

**Service identification** — Can you consistently answer: which service produced this signal, in which environment, at which version? Without this, every signal is ambiguous.

**Attribute standards** — Do your spans, metrics, and logs use consistent naming? Can you write a query that works across all services, or does each team invent its own attribute names?

**Implementation standards** — Does every service instrument errors the same way? Use the same SDK version? Apply the same context propagation rules?

**Operational standards** — Do you have data retention policies? Performance requirements for instrumentation overhead? Security guidelines for PII in telemetry?

Maturity means all four pillars advancing. A team with perfect tracing but no attribute standards, no retention policy, and no error handling convention is not at Level 3 — it just has expensive traces.

## The Five Levels

**Level 1 — Reactive**

Logs exist. Alerting is threshold-based or absent. Incidents are surprises. The question "why did this break?" requires an engineer who knows the code, not an engineer who knows the tooling.

Indicators:
- Unstructured logs, no correlation between signals
- Alerts are static thresholds set once and never reviewed
- No SLOs, no error budgets
- Post-incident reviews focus on what to fix, not what to instrument next

**Level 2 — Structured**

Structured logs, basic metrics, some dashboards. Manual on-call that leans on dashboards. Incidents are still surprises but are resolved faster because signals exist.

Indicators:
- JSON-structured logs with consistent fields
- Prometheus or equivalent collecting standard metrics
- Dashboards covering the RED signals for main services
- Basic alerting on error rate and latency
- No trace correlation yet

**Level 3 — Correlated**

Traces, logs, and metrics correlated. SLOs defined. Burn rate alerting. Incidents are often caught before users notice. This is the level where observability starts paying for itself.

Indicators:
- Distributed tracing covers all critical paths
- Trace IDs present in logs, enabling jump-from-log-to-trace
- SLOs defined for user-facing services with error budgets
- Multi-window burn rate alerts (fast and slow burn)
- Resource attributes are standardised (`deployment.environment`, `service.version`)
- Consistent error handling convention across services

**Level 4 — Proactive**

Anomaly detection, capacity planning from observability data, error budget reviews. The team catches problems before they become incidents. Observability is part of the development lifecycle, not just operations.

Indicators:
- Baseline-relative alerting for at least some services
- Capacity planning uses historical metric trends, not guesswork
- Error budget reviews happen on a regular cadence (weekly or monthly)
- Observability requirements are in design docs and code review checklists
- CI/CD pipeline is instrumented — build and deploy events as telemetry
- Observability standards program exists with enforcement at the pipeline level

**Level 5 — Predictive**

ML-assisted operations, automated remediation, business outcomes linked to reliability signals. Observability is a competitive advantage, not just operational hygiene.

Indicators:
- MTTR is measured and declining quarter-over-quarter
- Some classes of incidents trigger automated remediation
- Business KPIs (revenue, conversion, retention) are correlated with reliability metrics
- Observability data feeds capacity planning and product decisions
- The platform team is a product team with internal customers

## Self-Assessment Checklist

For each level, the minimum bar to claim it:

| Capability | L1 | L2 | L3 | L4 | L5 |
|-----------|----|----|----|----|-----|
| Structured logs on all services | | ✓ | ✓ | ✓ | ✓ |
| Distributed tracing on critical paths | | | ✓ | ✓ | ✓ |
| Trace-log correlation (trace ID in logs) | | | ✓ | ✓ | ✓ |
| SLOs defined for user-facing services | | | ✓ | ✓ | ✓ |
| Burn rate alerting | | | ✓ | ✓ | ✓ |
| Standardised resource attributes | | | ✓ | ✓ | ✓ |
| Error budget review cadence | | | | ✓ | ✓ |
| Observability in design/review process | | | | ✓ | ✓ |
| CI/CD pipeline instrumented | | | | ✓ | ✓ |
| Automated remediation for any class | | | | | ✓ |
| Business KPI correlation | | | | | ✓ |

## The People and Process Dimension

Technology is the easiest part to change. The harder constraints are people and process.

At **Level 2**, the blocker is usually engineering discipline — getting all teams to emit structured logs and agree on attribute names. This is a standards and culture problem, not a tooling problem.

At **Level 3**, the blocker is usually organisational — who owns the SLO for a service that three teams touch? Who reviews the error budget? These are governance problems.

At **Level 4**, the blocker is usually prioritisation — observability-driven development requires time investment before incidents happen. That is hard to justify without data on its own ROI.

At **Level 5**, the blocker is usually executive alignment — the business case for ML-assisted operations requires connecting reliability to revenue, which requires a different kind of conversation.

## Common Traps by Level

**Trap at L1→L2:** Installing a full Prometheus + Grafana + Tempo + Loki stack before you have structured logs. You are building the display case before you have anything to display.

**Trap at L2→L3:** Instrumenting tracing without establishing resource attribute standards first. You will have traces with no `deployment.environment` tag and spend months backfilling.

**Trap at L3→L4:** Buying an AIOps platform before you have reliable SLOs. Anomaly detection on noisy data generates noise, not signal.

**Trap at L4→L5:** Automating remediation before you have high-confidence alert definitions. Automated remediation on false positives causes incidents, not prevents them.

## How to Use This Model

Use the checklist to identify your current level honestly. Then identify the single biggest gap between your current level and the next level. That gap is your next investment — not the tools three levels ahead.

The model is also useful for governance conversations: "we are at Level 2 and we want to reach Level 3 in two quarters" is a specific, measurable goal that can be resourced and tracked.

<!-- TODO: Add section on observability maturity assessment process (how to run the assessment) -->
<!-- TODO: Add section on governance review cadence at each level (how often to review standards, who owns them) -->
<!-- TODO: Cross-reference to building-observability-standards.md for the governance/review process -->
