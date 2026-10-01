---
title: "Writing Runbooks That Work at 3am"
date: 2026-10-01
draft: false
excerpt: "A runbook that's hard to follow under pressure isn't a runbook. It's a liability. Here's the anatomy of one that actually shortens incident response, and how to keep it true."
readtime: 11
tags: ["On-Call", "Alerting", "SLOs", "Reliability", "Operations", "Best Practices"]
---

A runbook answers one question: this alert fired, so what do I do now? That question gets asked under stress, usually at night, by someone who may not have touched the service in weeks. The runbook's job is to get them from "alert firing" to "problem understood" as fast as possible, while their thinking is at its slowest.

## Where the Runbook Starts

The response doesn't start in the runbook. [An Alert Without a Next Step Is Just Noise](/articles/alert-design-principles/) makes the case that the alert body *is* the first page of the runbook: what's broken, how fast it's getting worse, what's already been checked, and the first three steps. Everything here picks up where that alert body stops.

So don't repeat the alert body in the runbook. Link the alert straight to the right section. Alert annotations are free-form, so pick one key for the link and use it on every alert. [How to Set Up Your First SLO and Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) uses `runbook`, and `runbook_url` is another common choice. Point it at the exact anchor for this alert, not the top of a wiki page.

The decision to follow a runbook or improvise should be fast too:

{{< mermaid caption="Fig. — Every path ends with the runbook being written or corrected, including the ones that needed help." >}}
flowchart TD
    A[Alert fires] --> B{Runbook for it?}
    B -->|Yes| C[Follow the runbook]
    B -->|No| D[Investigate and diagnose]
    C --> E{Resolved?}
    D --> E
    E -->|Yes| F[Create or update the runbook]
    E -->|No| G[Escalate]
    G --> H[Resolved with help]
    H --> F
{{< /mermaid >}}

Every incident that ends in improvisation is a chance to close the gap. If you fixed it, you now know the steps. Write them down before you close the ticket. That goes double for incidents you had to escalate, because those are the ones the next person is least likely to work out alone.

## Runbook Anatomy

A runbook for one alert has six sections, in this order. Each one serves the on-call engineer at a specific moment, so don't merge or reorder them.

### 1. Alert Details

What fired, and what that means in plain language:

```text
Alert: checkout-service ErrorBudgetFastBurn
Fires when: burn rate above 14.4x over both the last hour and the last
            5 minutes (99.9% SLO)
Means: 2% of the 30-day error budget gone in an hour. At this rate the
       whole budget lasts about 2 days (30 / 14.4).
```

Use the exact alert name from your paging system. The engineer arrives here from a page, so the name on the page and the name on the runbook should match character for character. The 14.4× fast-burn threshold over a 1-hour and a 5-minute window is the one the [SLO guide](/guides/slos-and-error-budgets/) uses, so the runbook and the alert speak the same language.

### 2. Likely Causes

List the three to five most common causes, ordered by how often they happen or how quickly you can rule them out, whichever gets the engineer to the answer faster. It's a starting point weighted by probability, not an exhaustive list.

```text
Likely causes (example shares from past postmortems):
1. Payment gateway timeout       ~60%
2. Database connection pool exhausted  ~25%
3. Regression from a recent deploy     ~10%
4. Cloud provider or network problem   ~5%
```

Those numbers should come from your own postmortems, and each postmortem should update them. A cause list nobody's revised since launch is a guess with a confident font.

### 3. Diagnostic Steps

Step by step, how to confirm or rule out each cause. Every step should be something you can execute, not a general direction:

{{< mermaid caption="Fig. — A diagnostic tree that ends in a named cause and a remediation section, or in escalation." >}}
flowchart TD
    A[Alert fires] --> B{Gateway latency<br/>over 5s?}
    B -->|Yes| C{Gateway errors<br/>in the logs?}
    B -->|No| D{DB pool over<br/>90% in use?}
    C -->|Yes| E[Gateway timeout<br/>see 4.1]
    C -->|No| D
    D -->|Yes| F[Pool exhausted<br/>see 4.2]
    D -->|No| G{Deploy in the<br/>last 2 hours?}
    G -->|Yes| H[Regression<br/>see 4.3]
    G -->|No| I{Provider status<br/>degraded?}
    I -->|Yes| J[Infrastructure<br/>see 4.4]
    I -->|No| K[Unknown cause<br/>escalate, section 5]
{{< /mermaid >}}

Good steps name the exact dashboard panel, query or command:

```text
Step 1: Gateway latency
  Grafana: "Checkout service" dashboard, "External gateway latency" panel
  Logs:    kubectl logs -n checkout -l app=checkout-api --since=15m \
             --tail=-1 --prefix --timestamps | grep -i gateway | sort -k2 | tail -50

Step 2: Database connection pool
  Metric:  checkout_db_pool_in_use / checkout_db_pool_max   (alert at 0.9)
```

Watch the defaults in commands you copy. With a label selector, `kubectl logs` shows only the last 10 lines per pod, so a bare `kubectl logs -l app=checkout-api | tail -50` can never show you 50 lines. It also prints the logs pod by pod, not in time order, so `tail` on its own mostly shows you the last pod. That's why the command above adds `--tail=-1` and `--since`, then `--timestamps` with `sort -k2` to put every pod's lines back in time order.

"Check the logs" and "look at the metrics" aren't steps. They create work instead of saving it.

### 4. Remediation

One subsection per cause from section 2. Each gives the action, what should happen, and how to verify it worked. Verify against the burn rate, the same signal that paged you, not a raw error percentage. With a 99.9% SLO, a 1% error rate is still burning budget ten times too fast. At low traffic a 5-minute window is noisy, so watch it for a few minutes rather than trusting one reading.

```text
4.1 Gateway timeout
  Confirm: the breaker-state metric your client library exports shows
           the circuit breaker open, and the gateway's latency or status
           page agrees. Don't grep the breaker's ConfigMap: that shows
           its settings, not whether it has tripped.
  Mitigate: switch to the fallback if you have one, such as a secondary
            gateway or queueing payments for retry instead of failing
            them. Turn off non-critical gateway calls (saved-card
            lookups, refund status) so checkout gets what's left.
  Know: while the breaker is open, calls fail fast, so errors stay high.
        After its configured reset timeout it lets a few trial requests
        through. It closes if they succeed and opens again if they fail.
  Escalate: to the gateway's owner (section 5) at the same time, not
            after you run out of ideas.
  Verify: 5-minute burn rate back under 1x within 10 minutes, and the
          1-hour burn rate falling.

4.2 Connection pool exhausted
  Action: find what's holding connections: slow queries, a stuck batch
          job, or a leak after a recent change. Kill or fix the offender.
          If you need time, add replicas to spread the load:
            kubectl scale deployment/checkout-api -n checkout --replicas=6
          (check the database can take the extra connections first)
  Verify: pool use back under 70%, and the 5-minute burn rate under 1x.

4.3 Regression from a recent deploy
  Action: roll back first, debug later:
            kubectl rollout undo deployment/checkout-api -n checkout
            kubectl rollout status deployment/checkout-api -n checkout --timeout=5m
  Verify: 5-minute burn rate under 1x within 10 minutes of the rollout
          completing. Then open a ticket for the bad version.

4.4 Cloud provider or network problem
  Action: confirm on the provider's status page and your own network
          dashboards. If you have a tested failover runbook, follow it.
          If you don't, escalate. This isn't the moment to improvise one.
  Verify: same burn-rate check, after the provider recovers or the
          failover completes.
```

### 5. Escalation

When to escalate, to whom, and what to bring with you:

```text
Escalate to: #payments-oncall, or the payments team's paging schedule
When: the cause is on the gateway side, the cause is unknown, or there's
      no improvement 30 minutes after starting remediation
Include:
  - Current burn rate on both windows
  - Diagnostic steps already done, and what each showed
  - Your hypothesis, or the confirmed cause if you have one
```

Severity decides how fast that escalation has to land. The [severity guide](/guides/alert-severity-levels/) sets the acknowledgement times, so link to it instead of copying them into every runbook, where they'll drift. [On-Call Procedures](/guides/on-call-procedures/) covers the rest of the hand-off: who's primary, who's secondary, and when an incident commander takes over.

### 6. Recovery

What happens after the immediate problem is fixed:

```text
Recovery:
1. Confirm the 5-minute burn rate has stayed under 1x for 15 minutes
2. Update the status page: mark the incident resolved
3. Post in #incidents: "Checkout payment errors resolved at HH:MM UTC.
   Impact: ~N users for ~M minutes. Postmortem to follow."
4. Revert anything temporary: extra replicas, config overrides, feature
   flags flipped during the incident
5. Open a postmortem if your policy calls for one for this severity
```

## Templates for Common Alert Types

Most alerts fall into a handful of shapes, and each shape has the same usual suspects. Start a new runbook from the matching template instead of a blank page:

| Alert type | Usual suspects | First check |
|---|---|---|
| Latency SLO burn | A slow dependency, CPU throttling, garbage collection, a cold cache | Latency broken down by dependency, then CPU throttling on the slow pods |
| Error-rate SLO burn | A bad deploy, a failing dependency, an expired secret or changed config | Errors by version and by dependency |
| Saturation (pool, queue, disk) | A traffic spike, a leak, a consumer that slowed down | The trend over the last few hours, then per-instance outliers |

The template gives you sections 2 and 3 in rough form. The postmortems fill in the real numbers.

## Runbooks as Code

Keep runbooks next to the alert rules they belong to, in the same repository, changed in the same pull request. An alert rule that changes without its runbook is a runbook that just went stale, and code review is the cheapest place to catch it.

Some steps deserve automation. The safe, reversible ones are good candidates: a rollback, restarting a stuck worker, turning a feature flag back off. Scaling out only belongs on that list when the bottleneck isn't a shared dependency. If the database is the problem, more replicas bring more connections and make it worse, as section 4.2 warns. Automate the safe steps and keep the human for the judgement calls: whether to fail over, when to escalate, what to tell customers. If an automated step can't be undone, it doesn't belong in automation yet.

## Keeping Runbooks Alive

Runbooks decay. The service changes and the runbook doesn't. A few habits keep them honest:

- **One click from the page.** If finding the runbook takes three wiki clicks at 3am, it doesn't exist.
- **Update it before you close the incident.** One corrected line per incident adds up to a runbook you can trust.
- **Put an owner and a "last verified" date at the top.** A date from two years ago is a warning, not a footnote.
- **Watch the runbook follow rate.** If on-call engineers stop opening a runbook, either it's not useful or the alert body already says enough. Both are worth knowing, and [the alert design article](/articles/alert-design-principles/) defines it.
- **Rehearse.** Walk through a runbook during a quiet week, or in a game day, before an incident tests it for you.

A runbook nobody reads at 2pm will fail somebody at 3am.

## See Also

- [An Alert Without a Next Step Is Just Noise](/articles/alert-design-principles/) — the alert body that hands off to the runbook
- [Alert Severity Levels, Rebuilt for Burn Rate](/guides/alert-severity-levels/) — who gets paged, how fast, and when to escalate
- [On-Call Procedures: From Page to Postmortem](/guides/on-call-procedures/) — rotations, hand-offs and postmortems around the runbook
- [SLOs and Error Budgets](/guides/slos-and-error-budgets/) — the burn rates these runbooks verify against
- [How to Set Up Your First SLO and Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) — building the alerts that page you here
