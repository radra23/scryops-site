---
title: "Migrating from Proprietary Agents to OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "Ripping out the Datadog agent and replacing it with OTel is not a weekend project. A systematic guide to planning, executing, and validating a migration from proprietary observability agents to OpenTelemetry — without losing coverage."
readtime: 10
tags: ["OpenTelemetry", "Collector", "Observability", "Cost"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. Why migrate: cost, portability, standardisation, flexibility
2. Migration risk: what you can lose if done wrong
3. Pre-migration inventory: mapping all existing instrumentation and dashboards
4. Side-by-side approach: running OTel and proprietary agent in parallel
5. Datadog Agent → OTel Collector migration specifics
6. New Relic APM → OTel migration specifics
7. Validating signal equivalence: ensuring new data matches old
8. Dashboard migration: recreating existing views in a new backend
9. Cutover strategy: gradual vs big-bang
10. Rollback plan
11. Post-migration: decommissioning the old agents
-->
