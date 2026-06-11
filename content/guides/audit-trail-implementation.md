---
title: "Implementing Audit Trails with OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "An audit trail is not a log. It's a tamper-evident, time-ordered record of who did what, when, and why. Most teams build this wrong. Here is how to do it correctly using OpenTelemetry and append-only storage."
readtime: 8
tags: ["Compliance", "Security", "OpenTelemetry", "Logs", "Privacy"]
---

<!-- TODO: Draft this guide -->
<!--
Sections to cover:
1. Audit trail vs application log: different requirements, different tooling
2. Regulatory requirements for audit trails (SOC 2, HIPAA, GDPR, PCI DSS)
3. Properties of a compliant audit trail: tamper-evidence, completeness, integrity
4. What to audit: user actions, admin operations, data access, configuration changes
5. Implementing audit events as OTel spans (actor, action, resource, outcome)
6. Storage requirements: append-only, long retention, immutability
7. Backend options: AWS CloudTrail, object storage with WORM, Loki with immutability
8. Querying audit trails: access patterns and tooling
9. Audit trail alerting: detecting suspicious patterns
10. Testing your audit trail implementation
-->
