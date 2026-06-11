---
title: "What is an SLI and how do you choose one?"
date: 2026-06-10
draft: true
answer: "An SLI (Service Level Indicator) is a quantitative measure of some aspect of your service's behaviour from the user's perspective. The best SLIs measure what users actually care about — not server-side proxies. Choose the metric that, when it degrades, users notice."
excerpt: "An SLI is a quantitative measure of service behaviour from the user's perspective. Choose the metric that, when it degrades, users notice — not server-side proxies that feel measurable but don't map to user experience."
readtime: 2
tags: ["SLOs", "Reliability", "Observability"]
---

<!-- TODO: Draft this Q&A -->
<!--
Answer should cover:
- SLI definition: a carefully defined quantitative measure
- The SLI → SLO → error budget chain
- Good SLI examples: request success rate, latency at p95, freshness of data
- Bad SLI examples: CPU utilisation, memory usage (proxy metrics, not user-facing)
- The "would a user notice?" test for SLI selection
- SLI types: availability, latency, throughput, error rate, freshness, durability
- Brief pointer to the SLI selection guide for service-type matrices
-->
