---
title: "Multi-Cluster Kubernetes Observability: Correlation Without Chaos"
date: 2026-06-10
draft: true
excerpt: "A request that crosses cluster boundaries breaks your traces and your dashboards. How to design observability architectures that give you end-to-end visibility across multiple Kubernetes clusters without centralising everything into a single point of failure."
readtime: 10
tags: ["Kubernetes", "OpenTelemetry", "Tracing", "Observability", "Multi-Cloud"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. The multi-cluster observability problem: spans that stop at cluster boundaries
2. Cross-cluster trace propagation: W3C Trace Context over network calls
3. Collector topology for multi-cluster:
   - Per-cluster DaemonSet agents → per-cluster gateway → central aggregator
   - Thanos for multi-cluster Prometheus federation
4. Cluster identity in telemetry: k8s.cluster.name and cluster-level resource attributes
5. Cross-cluster correlation in Grafana: linking traces to logs to metrics across clusters
6. Multi-tenant considerations: namespace and team isolation of telemetry
7. GitOps observability: watching ArgoCD/Flux sync events as telemetry
8. Network policy observability with Cilium Hubble
9. Cost attribution across clusters
10. Tools: Thanos, Cortex, Grafana Mimir for multi-cluster metrics
-->
