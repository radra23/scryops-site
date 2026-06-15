---
title: "Logs Are a Monitoring Layer. Most Teams Use Them as a Forensics Archive."
date: 2026-06-10
draft: true
excerpt: "Your logs are already capturing what metrics miss. The error rate says something is wrong. The logs say exactly which user, which operation, and which line of code. That difference is the whole gap between knowing and understanding."
readtime: 6
tags: ["Logs", "Observability", "Alerting"]
---

Most teams treat logs as the thing you look at after the alert fires. The metrics page, the dashboard, the burn rate — those are monitoring. Logs are for the investigation. That split is costing you incidents you could have caught earlier, and resolutions that take twice as long as they should.

Logs are not a forensics archive. They are a real-time signal stream. The distinction changes what you instrument, how you structure your events, and what you wire up for alerting.

## What Metrics Can't Tell You

Metrics aggregate. That is their strength — a single number summarises thousands of requests per second. It is also the ceiling. When your error rate climbs to 4%, the metric tells you that 4% of requests are failing. It doesn't tell you which endpoint, which customer, which order ID, or which dependency is returning the error.

Logs tell you all of those things. The individual event is the unit. Every field is queryable. The information is already there — most teams just aren't monitoring with it.

Picture the same incident from two vantage points. The metrics dashboard shows an error rate climbing from 0.8% to 4.2% between 14:20 and 14:35 UTC. The on-call engineer sees the spike, opens a runbook, and starts checking services. Five minutes in, they still don't know where to look. The metric is an alarm, not a diagnosis.

The log stream at 14:22 UTC shows something different: `payment-api` returning HTTP 402 on `/checkout/confirm`, exclusively for requests where `gateway="stripe"` and `card_status="expired"`. The error is not spreading. It is not a cascade. It is one specific condition on one specific endpoint, affecting a specific customer segment. The log stream had that answer at 14:22. The metrics page never will.

The metric told you something was wrong. The log told you what.

{{< obs-logs-vs-metrics >}}

## The Signal Hidden in Structured Logs

Free-text logs are searchable. Structured logs are queryable. That gap determines what your monitoring layer can actually do.

When a log line reads `"error processing payment for user 4821"`, you can grep for it. You can count occurrences. That's the extent of it. The string is the data, and the data is opaque. Every analysis requires pattern matching against uncontrolled human-written text.

When a log line is structured JSON — `{"event": "payment.failed", "error_type": "card_expired", "gateway": "stripe", "user_id": "4821", "endpoint": "/checkout/confirm"}` — every field is an independent dimension. You can filter on `gateway`, group by `error_type`, count distinct `user_id` values, and set an alert on any combination. The same event that was a string becomes a data point in a queryable dataset.

This is not a tooling difference. It is an instrumentation decision, made the moment you write the log call. A team that writes `logger.error("payment failed")` has committed to string matching for that event, forever. A team that writes `logger.error("payment.failed", extra={"gateway": gateway, "error_type": err.code, "user_id": user.id})` has committed to a monitoring capability. The log store you query it with — whether that's Loki, OpenSearch, Datadog, or anything else — is secondary. The field structure is what matters, and that lives in your application code.

Field consistency matters as much as field presence. A `level` field that alternates between `error`, `ERROR`, `err`, and `Error` across services forces every query to account for the variation. Canonical field names — agreed once, enforced via shared logging libraries — mean queries work across service boundaries without per-service normalization.

## Log-Based Alerting: What It Catches That Thresholds Miss

Metric thresholds are calibrated to aggregate behavior. They're tuned to ignore noise — a 0.5% error rate fluctuation, a 10-second p99 spike. That tuning is correct for catching broad degradations. It is systematically wrong for catching narrow failures.

Three failure patterns that are invisible to rate metrics but obvious in log fields:

A specific payment gateway returns 402s on a subset of transactions. The volume is not enough to move the aggregate error rate above any alert threshold. But `gateway="stripe" AND http_status=402` is a clean log filter with zero false positives. An alert on that field combination fires immediately. The affected customers see failures. The metric sees rounding error.

A high-traffic customer segment hits an undocumented rate limit on a third-party dependency. The overall error rate is normal — the segment is a small fraction of total traffic. But `customer_tier="enterprise" AND error_type="rate_limit"` is spiking in the log stream. The customers affected are the ones most likely to call your account team at 9am. The metric never sees it coming.

A retry storm is underway. Individual request error rates look normal because the retries eventually succeed. But the same `request_id` or `user_id` appears fifteen times in sixty seconds. Nobody instrumented a metric for client-side retry frequency. It's not a counter anyone thought to expose. The log stream captures it as a natural consequence of logging each attempt — the pattern is there if you look for it.

In all three cases, the log alert is not a fallback for absent metrics. It is a fundamentally different kind of check. Metrics summarize populations. Log-based alerts target specific conditions within those populations. The monitoring capability is not redundant — it's orthogonal.

{{< mermaid >}}
flowchart LR
    failure["Narrow failure\n(gateway=stripe, 402)"]

    subgraph metric["Metric threshold"]
        m1["Error rate: 4.0%\nthreshold: 5%"]
        m2["No alert fires"]
    end

    subgraph log["Log-based alert"]
        l1["gateway=stripe\nAND http_status=402"]
        l2["Alert fires immediately"]
    end

    failure --> m1
    m1 --> m2
    failure --> l1
    l1 --> l2

    style m2 fill:#2A1A1A,stroke:#CD384B,color:#FF6060
    style l2 fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41
{{< /mermaid >}}

## The Right Mental Model

Metrics, traces, and logs are not three ways of capturing the same thing. They answer different questions at different resolutions and at different query costs.

Metrics answer "what changed?" — aggregate behavior over time. They're cheap to store, fast to query, and appropriate for dashboards and burn rate calculations. Traces answer "where in the request path?" — the sequence of spans across services that a single request traversed. Logs answer "what specifically happened?" — the full event record at the moment something occurred, with every field your instrumentation captured.

Resolution is the defining difference. A metric is a summary. A log is an individual event. That makes logs expensive to query at scale and precise for specific conditions. Querying a week of logs across all services for a field combination you didn't index is slow and costly. Querying a fifteen-minute window with a specific filter is fast and cheap. The query pattern matters.

The common mistake is treating logs as a fallback — the thing you reach for when metrics aren't sufficient. That framing keeps logs in the forensics role. The correct model is that logs are the layer you use when metrics are not specific enough for the question you're asking. Metrics and logs coexist. They don't substitute for each other.

## Three Prerequisites

Structured log output with consistent field names across services. Not structured in one service and free-text in another. Not `error_type` here and `err_code` there. Canonical field names, enforced by a shared logging configuration or wrapper library. Without consistency, log-based alerts written against one service's schema break silently when events come from another service.

A query-ready log store. Real-time alerting requires low-latency queries against recent data. Cold storage — S3 Glacier, cheap archival tiers — cannot be the primary monitoring layer. The store needs to support field-level filtering on recent ingestion windows at alerting latency. Most purpose-built log platforms do. Object storage alone does not.

Volume control for high-frequency services. Log everything in development. In production, high-frequency `INFO` events on hot paths — health check responses, per-request debug traces — can make field-level queries cost-prohibitive before they add monitoring value. A filtering or sampling strategy for high-volume, low-signal events keeps the log store focused on what matters. Errors and warnings at full fidelity; verbose debug events sampled or dropped at the collector.

Start with what you already investigate manually. If there is a dashboard you open after every deployment, the conditions you check on that dashboard are the right place to wire your first log-based alert. The log fields that would tell you immediately what you currently discover by clicking around — those are the fields to alert on. Automate the manual check.
