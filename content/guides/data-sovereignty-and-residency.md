---
title: "Telemetry Data Sovereignty: Where Your Data Lives Matters"
date: 2026-06-10
draft: true
excerpt: "A distributed system that spans continents generates telemetry that spans legal jurisdictions. A guide to designing observability architectures that respect data residency requirements without sacrificing cross-region correlation."
readtime: 8
tags: ["Compliance", "Privacy", "GDPR", "Multi-Cloud", "Observability"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. What data sovereignty means for observability (telemetry as regulated data)
2. Key regulations with geographic data residency requirements:
   - GDPR: EU data cannot leave EEA without adequacy decision or SCCs
   - Germany: BSI requirements for critical infrastructure
   - China: PIPL and data localisation requirements
   - Russia: data localisation law
3. Architectures for regional telemetry isolation:
   - Per-region OTel Collector deployments with no cross-region forwarding
   - Regional backends (Grafana Cloud regional tenants, self-hosted per region)
   - Selective cross-region: aggregate/anonymised data only
4. The correlation problem: debugging cross-region issues when data can't move
5. Trade-off framework: compliance vs operational visibility
6. Implementation patterns in OTel Collector for geo-routing
7. Documentation and audit requirements
-->
