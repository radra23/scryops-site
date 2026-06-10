---
title: "Automated Remediation: When to Let the System Fix Itself"
date: 2026-06-10
draft: true
excerpt: "Automation that fixes problems is appealing. Automation that makes them worse at 3am is a nightmare. This guide covers safe patterns for automated remediation — what to automate, what to gate on human approval, and how to build in circuit breakers."
readtime: 9
tags: ["AIOps", "AI", "Reliability", "On-Call", "Observability"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. The automation spectrum: manual → assisted → semi-automated → autonomous
2. Prerequisites: you need solid observability before you automate anything
3. Safe automation candidates: pod restarts, circuit breaker trips, cache flushes, scaling events
4. Dangerous automation candidates: database operations, traffic routing, config changes
5. Circuit breakers for automation: stop conditions, escalation thresholds
6. Human-in-the-loop patterns: approval gates, confirmation windows
7. Runbook-as-code: encoding tribal knowledge as automatable playbooks
8. Tools: PagerDuty Automation, Rundeck, GitHub Actions for ops, Argo Events
9. Audit trails for automated actions (observability of your observability automation)
10. Post-automation review: how to verify the fix worked
-->
