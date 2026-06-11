---
title: "On-Call Procedures: From Page to Postmortem"
date: 2026-06-11
draft: true
excerpt: "A page is just the starting gun. What happens between the alert firing and the postmortem closing determines whether your team gets better or just gets tired."
readtime: 6
tags: ["On-Call", "Alerting", "Reliability", "Observability", "Operations"]
---

On-call is a machine. Like any machine, it either gets designed or it gets improvised — and improvised on-call is the kind that burns people out, misses incidents, and produces postmortems nobody reads. The sections below lay out the components: roles, rotation, triage, handoffs, and postmortems. Each is a gear. None works without the others.

{{< mermaid >}}
flowchart TD
    A[Monitor] --> B[Detect]
    B --> C[Respond]
    C --> D[Resolve]
    D --> E[Postmortem]
    E --> F[Improve]
    F --> A
{{< /mermaid >}}

The cycle is intentional. The postmortem feeds back into the monitoring layer — new thresholds, new runbook steps, new alerts for failure modes you hadn't considered. Without that feedback loop, on-call is just reactive. With it, each incident makes the next one shorter.

## Roles and Responsibilities

On-call works best with two roles in rotation simultaneously: a primary who owns detection and response, and a secondary who provides backup escalation and covers gaps.

{{< mermaid >}}
flowchart TD
    A[Primary On-Call] --> B[Detect and Respond]
    A --> C[Escalate if Needed]
    D[Secondary On-Call] --> E[Assist Primary]
    D --> F[Take Over if Primary Unavailable]
{{< /mermaid >}}

The boundary between the roles should be written down, not negotiated during an incident. Common conventions:

- Primary acknowledges all pages within the SLA (typically 5–15 minutes depending on severity); secondary covers if primary doesn't acknowledge within a grace window
- Primary drives communication — status page updates, stakeholder pings, postmortem authorship
- Secondary does not self-activate; primary explicitly hands off or requests backup
- Both roles rotate on the same schedule so secondary experience is real, not theoretical

Document the expectations in the team runbook. Engineers who haven't read the expectations before they're on-call will invent their own, usually incorrectly.

## Rotation Schedule

A fair rotation balances on-call load across the team and accounts for time zones, weekends, and holidays. The standard pattern is a weekly primary/secondary flip with a one-week offset between the two roles:

{{< mermaid >}}
gantt
    title On-Call Rotation (4-person team)
    dateFormat  YYYY-MM-DD
    section Engineer A
    Primary    :a1, 2026-06-08, 7d
    Secondary  :a2, after a1, 7d
    section Engineer B
    Secondary  :b1, 2026-06-08, 7d
    Primary    :b2, after b1, 7d
    section Engineer C
    Primary    :c1, 2026-06-22, 7d
    Secondary  :c2, after c1, 7d
    section Engineer D
    Secondary  :d1, 2026-06-22, 7d
    Primary    :d2, after d1, 7d
{{< /mermaid >}}

Practical notes:
- Publish the schedule at least two rotation cycles in advance
- Have a lightweight swap process — a Slack thread with ack from the team lead is enough; bureaucratic swap processes get ignored under deadline pressure
- Track holiday coverage explicitly; do not assume "the calendar handles it"
- If the team is globally distributed across more than two time zones, a follow-the-sun model reduces unsociable hours — but requires clean handoff documentation at each shift boundary

<!-- TODO: Add specific tooling configuration (PagerDuty schedule setup, Opsgenie escalation policies) -->

## Alert Routing by Severity

Not every alert warrants a page. Route based on the urgency of required action, not on the technical severity of the condition.

{{< mermaid >}}
flowchart LR
    A[Alert fires] --> B{Severity}
    B -->|Critical / P0-P1| C[Page via PagerDuty<br/>immediate response required]
    B -->|Warning / P2| D[Slack notification<br/>next business hour response]
    B -->|Informational / P3-P4| E[Email or dashboard annotation<br/>review at next standup]
{{< /mermaid >}}

The alert routing policy and severity definitions are covered in [Alert Severity Levels](/guides/alert-severity-levels/) and [Alert Design Principles](/guides/alert-design-principles/). The key constraint: if an alert fires and no action is required, it should not be in the paging channel. Every page trains the on-call engineer on what a page means. Page noise is learned helplessness.

## Incident Response

When a page fires, the first step is triage — establishing severity before committing resources. The triage decision determines who gets engaged, how fast, and what communication channels open.

{{< mermaid >}}
flowchart TD
    A[Incident Detected] --> B[Assess Severity]
    B --> C{Severity Level}
    C -->|Sev1 / P0| D[Activate Incident Response<br/>bridge, incident commander,<br/>status page update]
    C -->|Sev2 / P1| E[Investigate and Mitigate<br/>primary + secondary engaged]
    C -->|Sev3 / P2| F[Monitor and Resolve<br/>primary only, escalate if needed]
    D --> G[Communicate to stakeholders]
    D --> H[Escalate if unresolved in SLA]
    D --> I[Resolve]
    E --> I
    F --> I
    I --> J[Postmortem]
{{< /mermaid >}}

Keep the triage step deliberate and short — under five minutes. The most common triage mistake is jumping to mitigation before establishing severity, which leads to P0-level urgency applied to a P2 problem (or the reverse).

<!-- TODO: Add concrete triage questions (how many users affected? is revenue impacted? is there a known workaround?) and link to runbook templates -->
<!-- TODO: Add incident communication templates (status page wording per severity, internal Slack update cadence) -->

## Handoffs and Escalation

Incidents that span shift boundaries require explicit handoff. A handoff without documentation is a context wipe — the incoming engineer restarts diagnosis from scratch.

{{< mermaid >}}
flowchart TD
    A[Incident in Progress] --> B[Handoff at Shift Change]
    B --> C[Update: current status,<br/>actions taken, next steps,<br/>open hypotheses]
    C --> D{Resolved?}
    D -->|Yes| E[Close Incident]
    D -->|No| F{Escalation Needed?}
    F -->|Yes| G[Escalate to Next Level<br/>or Incident Commander]
    F -->|No| H[Continue Working]
    G --> H
    H --> D
{{< /mermaid >}}

A minimum handoff note contains:
- Current status (is the incident actively degrading, stabilised, or in recovery?)
- What has been tried and ruled out
- The leading hypothesis
- Immediate next action
- Who else is engaged

This takes three minutes to write and saves thirty.

Escalation criteria should be pre-defined, not negotiated mid-incident. Common triggers: incident has been active for N minutes without a mitigation path identified; the failure domain has expanded; external dependencies (payment provider, cloud region) appear to be involved.

## Postmortems

Every significant incident produces a postmortem. The purpose is not accountability — it is systemic learning. A postmortem that identifies a person as the root cause has found the wrong root cause.

{{< mermaid >}}
flowchart TD
    A[Incident Resolved] --> B[Conduct Blameless Postmortem]
    B --> C[Reconstruct Timeline]
    C --> D[Identify Contributing Factors]
    D --> E[Determine Improvements]
    E --> F[Assign Action Items with Owners]
    F --> G[Implement Changes]
    G --> H[Track Progress]
    H --> I[Share Learnings with Team]
    I --> J[Feed Improvements Back<br/>into Monitoring / Runbooks]
{{< /mermaid >}}

A postmortem action item without an owner and a due date is decorative. Assign each item at the postmortem meeting; review open items at the next team sync. The loop closes when the monitoring layer reflects what you learned — a new alert, a tighter threshold, a runbook step that would have halved the time to detect.

<!-- TODO: Add postmortem template (timeline format, contributing factors section, action item table) -->
<!-- TODO: Define what constitutes a "significant incident" requiring a postmortem vs. a brief incident note -->

- [Alert Severity Levels](/guides/alert-severity-levels/) — burn rate–based P0–P4 framework
- [Alert Design Principles](/guides/alert-design-principles/) — what every alert must answer before it fires
- [Alert Fatigue Is an Observability Problem](/articles/alert-fatigue-is-an-observability-problem/) — why the right fix is signal quality, not quieter thresholds
