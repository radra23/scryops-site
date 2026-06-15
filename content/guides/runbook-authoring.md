---
title: "Writing Runbooks That Work at 3am"
date: 2026-06-11
draft: true
excerpt: "A runbook that's hard to follow under pressure is not a runbook — it's a liability. This guide covers the anatomy of a runbook that actually shortens incident response time."
readtime: 6
tags: ["On-Call", "Reliability", "Observability", "Operations", "Best Practices"]
---

A runbook answers one question: given that this alert fired, what should I do now? That question gets asked under stress, often at night, by someone who may not have touched this service in weeks. The runbook's job is to get from "alert firing" to "issue understood" as fast as possible — and to be usable when the reader's cognition is at its worst.

The decision to follow a runbook or improvise should itself be fast:

{{< mermaid >}}
flowchart TD
    A[Incident] --> B{Runbook Available?}
    B -->|Yes| C[Follow Runbook]
    B -->|No| D[Investigate and Diagnose]
    C --> E{Resolved?}
    D --> E
    E -->|Yes| F[Document — Create or Update Runbook]
    E -->|No| G[Escalate per On-Call Procedures]
{{< /mermaid >}}

Every incident that ends in improvisation is an opportunity to close the gap. If you resolved it, you now know the runbook steps. Write them down before you close the ticket.

## Runbook Anatomy

A runbook for a specific alert should contain the following sections in order. Each section serves the on-call engineer at a specific stage; do not collapse or reorder them.

### 1. Alert Details

What alert triggers this runbook, and what does the triggering condition mean in plain language?

```
Alert: checkout-service ErrorRateBudgetBurn
Fires when: 1-hour burn rate > 14× (fast-burn threshold)
Means: Error budget will exhaust in ≤ 2.1 days at current rate
```

Include the exact alert name as it appears in the paging system. The on-call engineer will land on this runbook from a paged alert; make that link explicit.

### 2. Potential Causes

List the three to five most common causes for this alert, ordered by frequency or ease of diagnosis — whichever gets the engineer to the answer faster. This is not an exhaustive list; it is a probability-weighted starting point.

```
Most likely causes (in order):
1. Upstream payment gateway timeout (60% of occurrences)
2. Database connection pool exhausted (25%)
3. Recent deployment introducing regression (10%)
4. Infrastructure / cloud provider issue (5%)
```

Maintaining this list is an output of postmortems. After each incident, update the frequency estimate.

### 3. Diagnostic Steps

Step-by-step instructions for confirming or ruling out each potential cause. Each step should be a specific, executable action — not a general directive.

{{< mermaid >}}
flowchart TD
    A[Alert Triggered] --> B{Payment Gateway<br/>Latency > 5s?}
    B -->|Yes| C{Gateway Error Rate<br/>in Logs?}
    B -->|No| D{DB Connection Pool<br/>> 90% Utilised?}
    C -->|Errors Found| E[Cause: Gateway Timeout<br/>See Remediation §4.1]
    C -->|No Errors| D
    D -->|Yes| F[Cause: Connection Pool<br/>See Remediation §4.2]
    D -->|No| G{Recent Deploy<br/>in Last 2 Hours?}
    G -->|Yes| H[Cause: Regression<br/>See Remediation §4.3]
    G -->|No| I[Unknown Cause<br/>Escalate per §5]
{{< /mermaid >}}

Good diagnostic steps reference exact dashboard panels, log queries, or CLI commands:

```
Step 1: Check payment gateway latency
  → Grafana: Checkout Service dashboard, "External Gateway Latency" panel
  → Or: kubectl logs -n checkout -l app=checkout-api | grep "gateway" | tail -50
  
Step 2: Check DB connection pool
  → Metric: checkout_db_pool_utilisation (current value vs 90% threshold)
```

Ambiguous diagnostic instructions ("check the logs", "look at the metrics") create work instead of saving it.

### 4. Remediation Steps

Specific actions to take once the cause is confirmed. One subsection per cause identified in §2.

Each remediation should specify: the exact command or action, the expected outcome, and a verification step.

```
4.1 Gateway Timeout
  Action: The gateway has a circuit breaker — check if it has tripped:
    kubectl get configmap payment-gateway -n checkout -o yaml | grep circuit
  If open: it will self-recover in 5 minutes. Monitor error rate.
  If not tripped: escalate to #payments-oncall — this is a gateway-side issue.
  Verify: Error rate in Grafana should return below 1% within 10 minutes.
```

<!-- TODO: Add example remediation steps for DB pool exhaustion and regression rollback -->

### 5. Escalation Points

When to escalate, who to escalate to, and what information to provide when escalating.

```
Escalate to: #payments-oncall (Slack) or payment-team PagerDuty schedule
When: Issue is gateway-side, or unresolved after 30 minutes
What to include:
  - Current error rate and burn rate
  - Diagnostic steps already completed and results
  - Hypothesis or confirmed cause if known
```

### 6. Recovery Steps

Actions after the immediate issue is resolved: updating status pages, notifying stakeholders, cleaning up temporary fixes, and filing the postmortem trigger.

```
Recovery:
1. Verify error rate has dropped below SLO threshold for 15 minutes
2. Update status page: mark incident as resolved
3. Notify #incidents: "CheckoutService payment errors resolved at HH:MM UTC. 
   Impact: ~N users, ~M minutes. Postmortem to follow."
4. Revert any temporary config changes applied during incident
5. File postmortem if incident duration > 30 minutes or P0/P1 severity
```

## Runbook Storage and Maintenance

A runbook that is hard to find is nearly as bad as one that doesn't exist. Store runbooks in a location the on-call team can reach from a paging notification in one click — not buried three levels deep in a wiki.

Runbooks decay. The service changes; the runbook doesn't. Treat runbook accuracy as an output of your incident process: every time a diagnostic step turns out to be wrong or missing, update it before closing the ticket. A single-line addition per incident compounds into a genuinely reliable runbook over time.

<!-- TODO: Cover runbook-as-code patterns (encoding runbooks as automatable playbooks, linking to automated-remediation-playbooks.md) -->
<!-- TODO: Add guidance on runbook templates for different alert types (latency SLO burn, error rate SLO burn, saturation) -->

- [On-Call Procedures](/guides/on-call-procedures/) — escalation paths, handoff procedures, postmortem process
- [Alert Design Principles](/guides/alert-design-principles/) — what every alert body should include before it points to a runbook
- [Automated Remediation](/guides/automated-remediation-playbooks/) — when and how to encode runbook steps as automation
