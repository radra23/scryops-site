---
title: "Building Observability Standards for Your Organisation"
date: 2026-06-10
draft: true
excerpt: "A standards document nobody reads is worse than no standards document — it creates the illusion of governance without the reality. A guide to building observability standards that engineering teams actually follow: how to structure them, how to enforce them, and how to keep them alive."
readtime: 9
tags: ["Observability", "Best Practices", "Reliability", "Philosophy"]
---

Observability standards exist to answer a question that comes up at 2am: *how is this service instrumented and where do I look?* If engineers have to consult three wikis and two Slack threads to answer that question, the standards have failed — regardless of how well-written they are.

Good standards are short, enforceable, and evolve with the organisation. Bad standards are comprehensive documents that describe the ideal world and bear no relationship to what actually runs in production.

## What Standards Need to Cover

The minimum viable observability standards program covers four domains:

**1. Service identification** — How services name themselves, what resource attributes are required, and what values are acceptable for `deployment.environment`. This is the identity layer that makes all other telemetry queryable.

**2. Attribute conventions** — Naming rules for custom span attributes, required attributes per service type, and cardinality guidelines. Without this, every team invents its own attribute names and you cannot write cross-service queries.

**3. Implementation requirements** — Which OTel SDK version to use, which instrumentation libraries are required vs optional, how to handle errors, and minimum sampling configuration. This is the "how to instrument" section.

**4. Operational requirements** — Data retention expectations, performance overhead limits (instrumentation should not add more than X% latency), security guidelines for PII in telemetry, and alert coverage requirements.

## Structuring the Repository

A standards repository that mirrors the organisation's actual concerns:

```
standards/
├── implementation/
│   ├── core/              # Required for all services
│   ├── instrumentation/   # SDK and library requirements
│   ├── naming/            # Attribute and service naming rules
│   └── languages/         # Go, Java, Python, Node.js specific guides
├── telemetry/
│   ├── metrics/           # Metric naming and type conventions
│   ├── traces/            # Span attribute requirements
│   └── logs/              # Log schema and severity rules
├── operations/
│   ├── sampling/          # Sampling strategy requirements
│   └── exporters/         # Collector and exporter configuration
└── governance/
    ├── compliance/        # PII, GDPR, retention policies
    └── review/            # How standards are proposed and updated
```

## Enforcement Strategy

Standards without enforcement are suggestions. Three levels of enforcement:

**Automated (pipeline):** The OTel Collector enforces standards at the telemetry pipeline level. Use `transform` processors to normalise environment names, reject telemetry with missing required attributes, and tag non-compliant signals for review. This catches issues without requiring code changes.

**Automated (CI):** Linting checks in CI that verify SDK versions, required auto-instrumentation libraries are present in dependencies, and configuration files reference approved exporters.

**Manual (review):** Architecture review for new services ensures instrumentation requirements are covered in the design doc. Incident reviews use standards compliance as a dimension: did the service emit the telemetry needed to diagnose this?

The worst enforcement strategy: a Slack channel where you ask people to comply.

## The Review and Evolution Process

Standards that do not evolve die. The review process should be:

- **Quarterly review cycle** with explicit owners for each standards domain
- **Lightweight proposal process**: file an issue with the proposed change, the reason, and the migration path for existing services
- **Deprecation path for old standards**: mark old patterns as deprecated with a sunset date, not a hard removal
- **Changelog**: every standards update has a dated changelog entry so engineers can see what changed and when

## Common Failure Modes

**Standards as aspirational documents:** written for the ideal state, not the current state. Every service is out of compliance from day one.

**Centralised ownership without distributed buy-in:** the platform team writes the standards, everyone else ignores them. Standards work when service teams own compliance for their domains.

**Version drift:** SDK and library version requirements go stale as upstream releases. Nominate someone to track upstream releases and propose updates quarterly.

**Too much detail, not enough principle:** a 50-page standards document that specifies every attribute name will be ignored. A 5-page document that specifies naming rules and required attributes will be followed.

## Starting Small

If you have no standards today, start with three things:

1. `service.name` format and uniqueness requirement
2. `deployment.environment` closed vocabulary (`production`, `staging`, `development`)
3. Error handling contract (when to set `ERROR` span status)

These three cover 80% of the common problems. Everything else can be added incrementally.

<!-- TODO: Add section on the Collector as enforcement infrastructure (specific processor configs) -->
<!-- TODO: Add section on standards for different org sizes: startup vs mid-size vs enterprise -->
<!-- TODO: Add case study: what a standards migration looks like for an org with 50 services -->
<!-- TODO: Add section on community of practice: observability champions, office hours, guilds -->
