---
title: "Alert Correlation: Finding the Signal in the Flood"
date: 2026-10-01
draft: false
excerpt: "A single failure in a distributed system can trigger dozens of alerts across every layer it touches. Correlation groups the symptoms back into one cause — so the on-call engineer sees a problem, not a storm."
readtime: 6
tags: ["Alerting", "Observability", "Reliability", "On-Call", "AIOps"]
---

In a system with any meaningful depth, a single failure propagates. A database that stops responding makes the services querying it slow. Slow services make their upstream callers time out. Timed-out callers trigger their own circuit breakers, which fire their own alerts. One root cause; a dozen pages.

Without correlation, the on-call engineer receives that dozen pages and must manually reconstruct the causal chain under pressure. With correlation, they receive one grouped incident: "Database connectivity failure — 9 downstream services affected." That is not a minor UX improvement. The engineer starts from the likely cause instead of reconstructing it from twelve symptoms, at 3am, while the pager keeps going off.

{{< mermaid alt="Four alerts (DB timeout, Service A latency, Service B error rate, cache miss rate) are correlated into two incident groups: database connectivity failure and cache degradation" caption="Fig. — Four pages become two incidents, each named for its likely cause." >}}
flowchart LR
    A[Alert: DB Timeout] --> C{Correlate}
    B[Alert: Service A Latency] --> C
    D[Alert: Service B Error Rate] --> C
    E[Alert: Cache Miss Rate] --> C
    C --> F[Incident Group:<br/>Database Connectivity Failure]
    C --> G[Incident Group:<br/>Cache Degradation]
{{< /mermaid >}}

## Correlation Techniques

Correlation systems use one or more of the following techniques, typically in combination.

### Topology-Based Correlation

Map the dependency graph of your system. When an alert fires on a node, automatically group it with alerts from its downstream dependents. A database alert and a service-layer latency alert for a service that depends on that database are likely symptoms of the same cause.

{{< mermaid alt="Dependency graph: the web server calls the application server, which uses the database directly and through the cache" caption="Fig. — Alerts on a node and its dependents belong to one incident. Start from the node they all depend on." >}}
flowchart LR
    A[Web Server] --> B[Application Server]
    B --> C[(Database)]
    B --> D[Cache]
    D --> C
{{< /mermaid >}}

If `Database` and `Application Server` both alert within a short window, topology-based correlation assigns them to the same incident. The on-call engineer sees the root node — `Database` — rather than every downstream symptom separately.

This technique requires a service dependency map, which should already exist as part of your infrastructure-as-code or service mesh configuration. Incident platforms such as PagerDuty can model service dependencies directly. Prometheus Alertmanager has no dependency map, but you can encode the same idea in labels and inhibition rules, shown below.

### Temporal Correlation

Alerts that fire within a short time window often share a cause. Combine alerts that arrive close together into a single incident instead of paging for each one as it lands.

{{< mermaid alt="Temporal correlation: alerts A, B and C in the first five-minute window form incident group 1; alert D in a later window forms group 2" caption="Fig. — Alerts close together in time become one incident. Pair it with topology or semantic correlation." >}}
flowchart TD
    subgraph w1 ["Window 1: T+0:00 – T+0:05"]
        A["Alert A (T+0:00)"] ~~~ B["Alert B (T+0:02)"] ~~~ C["Alert C (T+0:03)"]
    end
    subgraph w2 ["Window 2: T+0:10 – T+0:15"]
        D["Alert D (T+0:10)"]
    end
    w1 --> G1[Incident Group 1]
    w2 --> G2[Incident Group 2]
{{< /mermaid >}}

Temporal correlation alone is imprecise — unrelated alerts can fire in the same window during busy periods. It is most effective when combined with topology or semantic correlation as a secondary filter.

### Semantic Correlation

Group alerts that describe the same failure mode across different services. An error-rate alert on Service A and an error-rate alert on Service B, firing within the same window, are more likely to share a cause than two alerts of different types.

{{< mermaid alt="Semantic correlation: error-rate alerts on services A and B form one incident group, latency alerts on services X and Y form another" caption="Fig. — The same failure type in the same window becomes one incident, which only works with consistent alert names." >}}
flowchart LR
    A[Error Rate: Service A] --> C{Correlate<br/>by Type + Window}
    B[Error Rate: Service B] --> C
    D[High Latency: Service X] --> E{Correlate<br/>by Type + Window}
    F[High Latency: Service Y] --> E
    C --> G[Incident Group:<br/>Error Rate Spike]
    E --> H[Incident Group:<br/>Latency Degradation]
{{< /mermaid >}}

Semantic correlation requires consistent alert naming conventions. An alert called `PaymentServiceErrorRate` and one called `InventoryHighErrorCount` will not be recognisably similar to a naive correlator. Give the same failure mode the same alert name everywhere, with the service as a label (`HighErrorRate{service="payments"}`), and grouping becomes a one-line config change.

## Using Correlation Output

Once alerts are grouped, the correlation output becomes an input to triage: is this a known failure mode? If so, trigger the runbook directly.

{{< mermaid alt="A correlated alert group that matches a known pattern triggers a runbook; otherwise it goes to on-call with the group as context" caption="Fig. — Known patterns go straight to a runbook. New ones reach a human with the correlation already done." >}}
flowchart TD
    A[Correlated Alert Group] --> B{Matches<br/>Known Pattern?}
    B -->|Yes| C[Trigger Runbook<br/>Automatically or with One-Click]
    B -->|No| D[Route to On-Call<br/>with Group as Context]
    C --> E[Automated or Guided Remediation]
    D --> F[Manual Investigation<br/>with Correlation as Starting Point]
{{< /mermaid >}}

The pattern-matching layer is where AIOps platforms add value: building a model of "what alert groups have appeared together historically, and what was the resolution?" That model makes the correlation output increasingly actionable over time. For teams without an AIOps platform, the same effect can be achieved manually: maintain a decision table in the runbook repository mapping known alert group signatures to runbooks.

<!-- TODO: Cover ML-based correlation approaches and when they add value over rule-based systems -->
<!-- TODO: Cover correlation in managed platforms (Datadog Event Correlation, PagerDuty Intelligent Alert Grouping) -->

## Implementing Correlation Step by Step

Start with the lowest-effort technique that covers your highest-pain alert patterns:

1. **Start with grouping** at the alerting platform level. In Prometheus Alertmanager, `group_by` decides which alerts share a notification, and `group_wait` is how long a new group waits for more alerts before the first page goes out.
2. **Add topology once you have a dependency map.** Even a manually maintained CMDB or service catalogue YAML file is enough to seed topology-based rules.
3. **Add semantic grouping** once alert naming is consistent across services. This requires enforcing naming conventions — ideally via alert rule linting in CI.
4. **Iteratively refine** based on false positives (unrelated alerts grouped) and false negatives (related alerts not grouped). Each incident postmortem should note whether the correlation was helpful, unhelpful, or missing.

Here's what the first three steps look like in Alertmanager:

```yaml
route:
  receiver: oncall-pager
  # Semantic: one notification per alert type per cluster, however many
  # services fire it. Grouping by service would split one cascade into
  # one page per service.
  group_by: ['alertname', 'cluster']
  # Temporal: wait this long for related alerts before the first page.
  # It delays every new page, so keep it short.
  group_wait: 30s
  # Then batch alerts that join an existing group.
  group_interval: 5m
  repeat_interval: 4h

inhibit_rules:
  # Topology: while the orders database is down, mute alerts from the
  # services that depend on it, in the same cluster. The dependency is
  # a depends_on label you set on those services' alert rules.
  - source_matchers:
      - alertname = "OrdersDatabaseDown"
    target_matchers:
      - depends_on = "orders-db"
    equal: ['cluster']

receivers:
  - name: oncall-pager
```

Two settings in that file are easy to get wrong. `group_wait` isn't a correlation window you can stretch to five minutes: it's the delay before the first page of every new group, P0s included. And inhibition only mutes the dependents. The database alert itself still pages, and it's the one with the cause in it.

The goal is not zero noise — it is the minimum noise consistent with catching every real incident. Correlation does not make alerts disappear; it makes the structure of incidents legible.

## See Also

- [Alert Design Principles](/articles/alert-design-principles/) — what every alert must contain before correlation can help
- [Alert Severity Levels](/guides/alert-severity-levels/) — burn-rate-based severity framework
- [On-Call Procedures](/guides/on-call-procedures/) — how correlated incidents flow into the incident response process
- [Runbook Authoring](/guides/runbook-authoring/) — writing the runbooks that correlation output points to
