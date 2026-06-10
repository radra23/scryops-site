---
title: "An Alert Without a Next Step Is Just Noise"
date: 2026-05-26
draft: false
excerpt: "The alert fires. The on-call is up. Now what? If the answer is 'check the dashboard,' the alert is still in progress. The alert body is where you fix the incident, or you end up losing hours chasing context."
readtime: 6
tags: ["Alerting", "On-Call", "SLOs", "Reliability", "Observability"]
---

> An alert that wakes you up without telling you what to do next is not an alert. It's an accusation.

It is 2 a.m. The alert fires. The on-call is awake, phone in hand. Now what?

If the answer is 'check the dashboard' or 'look at the logs' or 'figure out what is going on,' the alert is incomplete. Notifying is easy. Telling someone what to do is the hard part. Everything between notification and resolution depends on what the engineer can find in five minutes, under stress, probably squinting at a small screen.

The alert body is not metadata. It is the first page of the runbook. Write it that way.

## The Four Questions Every Alert Must Answer

A good alert answers four questions before the on-call even asks.

**What's broken?** Not the rule name. 'ErrorRateHigh' tells you nothing. What service, what operation, what user-facing behavior is actually degraded? 'Checkout service: payment processing error rate at 8.3% (SLO threshold: 1%). About 420 users per minute affected.'

**How fast is it getting worse?** That is the burn rate. At this rate, how long until the error budget runs out? 'Current burn rate: 8.3x. At this rate, monthly error budget exhausted in about 3.6 days.' This number decides if you wake up the team now or wait until morning.

**What has already been checked?** The alert system can add context automatically: recent deployments, correlated alerts, whether this happened before and how it was fixed. Not a list of dashboards to open. Curated context, delivered before the engineer forms a hypothesis.

**What are the first three steps?** Give the runbook link and the exact starting point. Not 'see runbook.' Instead: 'Runbook: payment-processing-errors, section 3: gateway timeout diagnosis.'

{{< obs-alert-two-designs >}}

Same alert, two designs: the lane that ships a next step, and the bare notification most teams send today.

## Before and After — Same Incident, Different Alert Bodies

Here's the difference good design makes. The same underlying condition — elevated error rate in the payment service — expressed two ways.

❌ **The notification (what most teams have):**

```
FIRING: PaymentServiceErrorRateHigh
Severity: P1
Value: 8.3%
Threshold: 1%
Service: payment-api
Dashboard: https://grafana.example.com/d/payment
```

✅ **The alert (what it should be):**

```
[P1] PAYMENT SERVICE DEGRADED — checkout errors at 8.3x normal rate

Impact: ~420 users/minute experiencing payment failures
SLO status: Monthly error budget 23% consumed, exhausted in ~67h at current burn
First seen: 02:14 UTC (11 minutes ago)

Recent changes:
  - payment-api v2.4.1 deployed 02:08 UTC (6 min before incident start)
  - No other services currently alerting

First steps:
  1. Check deployment health: kubectl rollout status deploy/payment-api
  2. If recent deploy is the cause: kubectl rollout undo deploy/payment-api
  3. If no obvious cause: Runbook → payment-errors → section 3 (gateway timeouts)

Runbook: https://runbooks.example.com/payment-errors#section-3
Trace sample: https://jaeger.example.com/trace/abc123def456
```

The second version does more than say something is wrong. It shows the blast radius, the time pressure, the likely cause from a deployment six minutes before, and the first command to run. An engineer who has never seen this alert can start diagnosing right away.

{{< insight lightbulb >}}
**The "recent changes" field** is often the most valuable line in the alert. Most incidents start with a recent change. If your alerting system can attach the last deployment timestamp and version, it gives the engineer the most likely cause before they start guessing. Make this field required.
{{< /insight >}}

## SLO Context Is Not Optional Decoration

Burn rate and time-to-budget-exhaustion are not extras. They are the main decision tools for the engineer who gets the alert.

A P1 with a 14x burn rate — the monthly budget draining in about two days instead of a month — means escalate now. The same P1 at a 2x burn rate, with roughly two weeks of budget left, is urgent, but you do not need to wake the backend lead at 2am. Without burn rate, the engineer has to look it up before acting. That is time the engineer does not have.

The multi-window burn rate gives you both responsiveness and confidence.

{{< obs-burn-rate-windows >}}

The 1-hour window drives the page. The 6-hour window shows if it is a spike or not. The 24-hour window tells you if this is new or has been getting worse all day.

## The Alert Lifecycle — From Creation to Retirement

Most teams focus on creating alerts. Few think about retiring them. The result is alert configs piling up. Rules for incidents from two years ago, thresholds set during a scaling crisis that are now always breached, duplicates from different monitoring systems that never got cleaned up.

{{< obs-alert-lifecycle >}}

The review questions are simple. What percentage of alerts led to real action? Did the engineer follow the runbook link or ignore it? Was the context enough, or did the engineer have to go hunting? Alerts that get acknowledged and closed without action fail the 'next step' test. They notify, but do not inform.

## Measuring Whether Your Alerts Are Working

Four numbers tell you most of what you need to know about alert quality.

**Time to acknowledge** shows if the paging path works and if engineers trust the alert. High TTAck on a P1 means something is broken.

**False positive rate** — the percentage of alerts that led to no action. Above 20 percent, you are training your team to ignore the alert. Above 50 percent, delete it and start over.

{{< obs-fp-rate-zones >}}

**Mean time to resolution** for alert-initiated incidents and those found another way. If alert-initiated incidents take longer, the alert is not giving useful context when it matters.

**Runbook follow rate** — did the on-call click the runbook link? If not, either the runbook is not useful or the alert body already had enough context to act. Both are worth knowing.

## The Connection to the Broader Model

An alert with SLO context, burn rate, and blast radius is not just better UX for the on-call. It shows a different model: observability as a system that tells you what is happening to users, not just which thresholds are crossed.

The question 'is this alert actionable?' is really asking, 'do I understand what this condition means for my users?' If you cannot write the 'first three steps' section, you have not traced the path from metric to user experience. The alert body is where you prove it.

Write your alerts as letters to your future self at 2 a.m.

{{< insight bookmark >}}
**A useful forcing function:** require every new alert to include a runbook section before it goes to production. If you cannot write the runbook section, the alert is not ready. You do not yet fully understand the condition you are alerting on. Writing the runbook section is often where the real design work happens.
{{< /insight >}}

{{< obs-mascot class="warrior" quip="An alert that wakes me with no next step? I draw my sword and charge into the dashboard. ...the sword does not help without a runbook, but it FEELS proactive." >}}
