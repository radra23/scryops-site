---
title: "Choosing SLIs for Your Service: A Practitioner's Matrix"
date: 2026-06-10
draft: true
excerpt: "Availability and latency are the obvious SLIs. But they don't fit every service type. This guide provides SLI selection frameworks for APIs, data pipelines, batch jobs, storage systems, event-driven services, and more."
readtime: 9
tags: ["SLOs", "Reliability", "Observability", "Metrics"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. SLI fundamentals recap (one section, link to existing SLO guide)
2. SLI selection principles: what makes a good SLI?
3. Service type matrix:
   - Synchronous APIs: availability, latency, error rate
   - Data pipelines: freshness, completeness, processing lag
   - Batch jobs: success rate, duration, data quality
   - Storage systems: durability, read/write availability, latency
   - Event-driven / async services: delivery rate, processing latency, dead-letter rate
   - Machine learning models: prediction latency, staleness, accuracy degradation
   - CDN / static assets: cache hit rate, origin availability
4. SLI anti-patterns: what not to use as an SLI
5. Composite SLIs for multi-component user journeys
6. Worked examples with PromQL for each service type
-->
