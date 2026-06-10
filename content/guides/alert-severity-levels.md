---
title: "Alert Severity Levels, Rebuilt for Burn Rate"
date: 2026-05-26
draft: false
excerpt: "The P0-P4 framework was built for a world of static thresholds. Here's how to reconnect it to SLO burn rates — so severity reflects actual user impact, not arbitrary lines."
readtime: 6
tags: ["Alerting", "SLOs", "On-Call", "Reliability"]
---

Severity levels are a promise to the person on the other end of the page. A P0 says: this cannot wait. A P2 says: this matters, but morning is soon enough. A P4 says: someone should know about this, but nobody needs to move.

Most severity frameworks were designed for a world of static thresholds — a metric crosses a line, you assign it a P-level, you page someone or you don't. That worked when systems were simpler and incidents were more discrete. It fails when you're trying to catch degradations before they become full outages. Static thresholds tell you what happened. Burn rate tells you what's happening. A modern severity framework needs to handle both.

## Five Levels, One Question

The P0-P4 scale is still useful — not as a prescriptive checklist, but as a shared language for "how fast do we need to move?" The question that matters: how fast is user experience degrading, and how long do we have before it becomes unacceptable?

**P0 — The Clock Is Running.** Complete outage or severe degradation affecting a large percentage of users. Revenue impact is active and direct. No workaround exists. Fast burn rate: error budget exhausted within roughly two days at the current rate. Response is immediate, all hands, round-the-clock until mitigated.

**P1 — Significant and Getting Worse.** Partial outage or major feature failure affecting a significant portion of users. Some revenue impact. Limited workarounds. Moderate burn rate: budget will exhaust in roughly five days at the current rate. Requires a dedicated response team, but a single on-call escalation is usually sufficient to start.

**P2 — Real, But Not an Emergency.** Non-critical functionality degraded, affecting a small subset of users. Minimal revenue impact. Usable workarounds exist. Slow burn but noticeable — worth investigating within the sprint, but nobody needs to be woken up for it. Addressed during business hours.

**P3 — Low and Stable.** Minor issues: cosmetic, edge-case, or affecting very few users with no meaningful business impact. No budget pressure. Handled in the normal sprint cycle.

**P4 — Informational.** No service impact. Purely observational — capacity thresholds, trend signals, things worth knowing about but requiring no action right now.

{{< mermaid >}}
flowchart TD
 subgraph subGraph0["Business Impact Assessment"]
        D["User Impact"]:::highlight
        E["Revenue Impact"]:::highlight
        F["SLO Burn Rate"]:::highlight
        S["Error Budget Remaining"]:::highlight
  end
 subgraph subGraph1["Severity Classification"]
        G["P0 / P1"]:::critical
        H["P2 / P3"]:::medium
        I["P4"]:::info
  end
 subgraph subGraph2["Response Protocol"]
        J["Notification Channel"]:::highlight
        K["Response Time SLA"]:::highlight
        M["Escalation Path"]:::highlight
  end
    subGraph0 --> subGraph1
    subGraph1 --> subGraph2

subGraph0:::back
subGraph1:::back
subGraph2:::back

classDef back fill:#F3F3F3,stroke:#D1D1D1,stroke-width:2px
classDef highlight fill:#E0F7FA,stroke:#00ACC1,stroke-width:2px
classDef critical fill:#FFEBEE,stroke:#F44336,stroke-width:2px
classDef medium fill:#E8F5E9,stroke:#4CAF50,stroke-width:2px
classDef info fill:#F3E5F5,stroke:#9C27B0,stroke-width:2px
{{< /mermaid >}}

## Let the Burn Rate Set the Level

The cleanest way to drive severity from observability data is to wire it to your SLO burn rate, not to individual metric thresholds. The mapping is straightforward once you see it.

A burn rate above 14x over one hour means your budget will exhaust in roughly two days — act immediately. That's a P0. A burn rate of 6x over six hours means you'll exhaust it in about five days — P1. A 2x burn rate sustained over three days is P2: real and worth fixing, but not worth disrupting anyone's night. Anything below 1x means you're operating within your error budget — P4 at most.

It's the approach that has replaced threshold-based paging at teams that have moved to proper SLO-based alerting. The advantage is proportionality: the severity reflects actual user impact, not whatever threshold someone set three years ago and never reviewed.

## Who Gets Woken Up, and When

The severity level should directly determine three things: who gets notified, through what channel, and by when. The channel matters as much as the time.

| Level | Notify via | Acknowledgment | After-hours? |
|-------|-----------|----------------|-------------|
| P0 | PagerDuty + call | < 5 min | Yes, 24/7 |
| P1 | PagerDuty | < 30 min | Yes, 24/7 |
| P2 | Incident channel | < 2 hours | Business hours |
| P3 | Ticket | < 8 hours | Business hours |
| P4 | Documentation | Next cycle | No |

A P2 that pages someone at 3am is a mismatch between severity and routing — even if the acknowledgment time is fast. Lower-severity alerts should go to passive channels that a team reviews during working hours, not active interrupt channels. Protecting the sleep of your on-call team isn't just kindness; it's a reliability investment. An engineer who has been woken up unnecessarily three times in a week will be slower to respond the fourth time, when it actually matters.

## When in Doubt, Go Higher

Not every incident arrives with a clear severity label. When the initial assessment is uncertain, default to higher severity and downgrade. A P1 that turns out to be a P2 costs the team some sleep. A P2 that should have been a P1 costs users.

Escalate when: the on-call responder can't resolve or contain within the expected window, the impact is spreading to additional services or customers, or the error budget burn rate increases after the initial response begins.

Document the escalation decision when it happens. Post-incident reviews that can trace why severity was reassigned — and when — surface the systemic gaps that reviews limited to resolution timelines miss entirely.

## The Framework That Never Reviews Itself Goes Stale

A severity framework written once and never revisited is a framework that slowly drifts out of alignment with how your system actually behaves. Business priorities change. Services get added. What counts as a P0 revenue impact for a company doing $1M/month is a different calculation from a company doing $10M/month.

Run a quarterly review: pull the last quarter's incidents, compare assigned severity to actual impact, and adjust the thresholds where they drifted. That's what keeps the framework calibrated before the gaps turn into outages.

A severity framework tied to real burn rate data will tell you when your P0 threshold is miscalibrated. One written to a whiteboard and never reviewed won't.

{{< insight bookmark >}}
**The test worth running.**
Pull your last 20 P0 and P1 incidents. For each one, check when the SLO burn rate first exceeded 6x — and when the alert actually fired. The gap between those two timestamps is how far behind your alerting is. For most teams, it's meaningful.
{{< /insight >}}
