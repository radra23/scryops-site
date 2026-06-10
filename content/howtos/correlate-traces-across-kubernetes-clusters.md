---
title: "How to Correlate Traces Across Multiple Kubernetes Clusters"
date: 2026-06-10
draft: true
excerpt: "When a request crosses a cluster boundary, your traces break. Fix this with proper W3C Trace Context propagation, cluster-aware Collector configuration, and a multi-tenant Tempo backend."
readtime: 7
tags: ["Kubernetes", "Tracing", "OpenTelemetry", "Collector", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. The problem: spans arrive in separate backends, cluster boundary breaks the trace
2. Prerequisite: W3C Trace Context headers on all inter-cluster HTTP calls
3. Add k8s.cluster.name as a resource attribute in each cluster's Collector
4. Configure per-cluster gateway Collectors with cluster identity labels
5. Set up Grafana Tempo multi-tenancy (one tenant per cluster, or unified)
6. Configure Tempo's load balancing exporter for trace-ID affinity (same trace → same replica)
7. Grafana: multi-tenant trace lookup across cluster tenants
8. Verify: trace a request from cluster A through cluster B, see both spans

Include: Collector config per cluster, Tempo configuration, Grafana datasource setup
-->
