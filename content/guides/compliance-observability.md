---
title: "Observability Under Compliance: GDPR, HIPAA, SOC 2, and PCI DSS"
date: 2026-06-10
draft: true
excerpt: "Regulated industries need observability too. A guide to building telemetry pipelines that satisfy GDPR, HIPAA, SOC 2, and PCI DSS requirements — covering data minimisation, retention mandates, audit trails, and what each framework actually requires."
readtime: 10
tags: ["Compliance", "Privacy", "GDPR", "Security", "Observability"]
---

Every regulated organisation faces the same contradiction: good observability means keeping detailed operational data, but good compliance means minimising and deleting personal data. These goals are not incompatible, but resolving them requires deliberate design.

The mistake most teams make is treating compliance as a post-hoc concern — instrument everything, then figure out what to redact. The right approach is the reverse: define what telemetry you legitimately need, then instrument only that.

## The Compliance-Observability Tension

Observability asks you to collect more data, more granularly, for longer. Compliance frameworks ask you to collect the minimum necessary, protect it rigorously, and delete it when it is no longer needed.

The resolution is not to choose one or the other — it is to be precise about what *necessary* means. Operational telemetry is legitimate data processing. A request duration, a database query count, and an error rate are necessary for operating a reliable service. A user's email address in a trace attribute, a national insurance number in an application log, or a raw SQL query containing bound parameters are not.

The goal: telemetry rich enough to debug, lean enough to comply.

## GDPR Requirements for Telemetry

The General Data Protection Regulation applies to any processing of personal data for EU and EEA residents — including processing for operational purposes. Observability data that contains personal identifiers is within scope.

**Lawful basis.** Every category of processing requires a documented lawful basis. For operational telemetry, *legitimate interests* (Article 6(1)(f)) typically applies: you process data to operate a reliable service, and that interest is not overridden by the data subject's rights. Document this reasoning explicitly in your Record of Processing Activities (RoPA). Vague references to "operational necessity" are not sufficient — name the purpose, the data categories, and why the interest is proportionate.

**Data minimisation (Article 5(1)(c)).** Telemetry must be adequate, relevant, and limited to what is necessary. In practice:
- Span attributes should identify operations, not individuals: `order.tier` rather than `user.email`
- Log fields should record events, not payloads: `request.path` rather than `request.body`
- Metrics should aggregate behaviour, not track people: `login.attempts_total` rather than recording individual user IDs

**Data protection by design (Article 25).** PII should not enter the telemetry pipeline in the first place. This is harder than it sounds — ORM frameworks log query parameters, HTTP middleware logs request bodies, and context propagation accumulates span attributes across services. Instrumentation code review is a data protection by design practice, not just a code quality practice.

**Data subject rights.** GDPR grants individuals the right to erasure (Article 17), access (Article 15), and portability (Article 20). Erasure is the hard one for telemetry, since most log and trace stores are append-only. Three practical approaches:

1. **Do not store personal data in telemetry.** If no personal data reaches the backend, there is nothing to erase. This is the strongest option — deletion rights become a non-issue.
2. **Tokenisation with a deletion-capable registry.** Replace personal identifiers with opaque tokens at the point of collection. Maintain a separate registry mapping tokens to individuals. On an erasure request, delete the mapping — the token remains in telemetry records but can no longer be linked to the data subject.
3. **Short retention for personal-data-containing signals.** If a small subset of signals unavoidably carries personal data, retain that subset for days rather than months. Most erasure requests are satisfied by normal expiry before action is required.

**International data transfers.** If your team is EU-based and your telemetry backend is US-hosted — Datadog US, New Relic, Grafana Cloud US — you are transferring personal data outside the EEA. This requires an adequacy mechanism: Standard Contractual Clauses (SCCs) with your vendor, or an EU-region deployment of the same service. Check your vendor's data processing addendum to confirm which SCCs are in effect. See [Telemetry Data Sovereignty](/guides/data-sovereignty-and-residency/) for the architectural patterns.

{{< insight >}}
The most common GDPR violation in observability is not deliberate. It is a developer adding `activity?.SetTag("user.email", user.Email)` for a debugging session and not removing it before merge. Instrumentation code review and CI checks for known PII attribute names catch this at source — more reliably than Collector scrubbing after the fact.
{{< /insight >}}

## Technical Controls: The Collector as Compliance Infrastructure

The OTel Collector is the practical enforcement boundary for compliance controls. Applied at the Collector, transformations run uniformly across every service — application teams do not need to handle compliance requirements individually.

For detailed Collector processor configurations — OTTL-based field redaction, pattern-matching scrubbing, and attribute allowlisting — see [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/).

Three Collector-level controls that matter for compliance specifically:

**Field scrubbing on ingest.** Remove or redact attributes that should never reach the backend. The `transform` processor with OTTL expressions handles this for traces, metrics, and logs uniformly. Apply it as the first processor in every pipeline — before any sampling decisions, so that redacted data is never written to disk even temporarily.

**Routing by data classification.** Tag signals at collection time with a retention class, then route different classes to backend configurations with different retention windows. High-sensitivity signals that cannot be fully stripped get a short-retention route; fully anonymised operational signals get the standard route. This automates the retention lifecycle without manual intervention per record.

**Pipeline audit logging.** The Collector should emit structured logs for administrative events — configuration reloads, authentication failures, exporter errors. These records are part of your compliance audit trail and must be stored separately from the operational telemetry pipeline they govern.

## Access Control for Telemetry Data

Telemetry backends are as sensitive as application databases. Access controls should reflect what each role actually needs, not default to "everyone on the engineering team gets full read access."

**Role tiers by access need:**

| Role | Access | Rationale |
|------|--------|-----------|
| Read-only observer | Aggregated metrics, pre-built dashboards | Situational awareness without raw trace data |
| Analyst | Full metrics, sampled traces with PII fields masked | Performance investigation, capacity planning |
| Service engineer | Full traces and logs scoped to their own services | Day-to-day development and debugging |
| Security auditor | Audit trail records, Collector access logs | Compliance reviews and incident investigations |
| Platform administrator | All signals plus pipeline configuration | Platform engineering only |

**Break-glass access.** During active incidents, engineers may need traces from services outside their normal scope. A break-glass mechanism should grant time-limited elevation with automatic audit logging: every query made during the elevated window is recorded with the requester identity, timestamp, and stated justification.

**Role-based field masking.** Some backends support field-level access controls — analysts see masked email fields, on-call engineers see unmasked fields during an active incident. This allows the same telemetry record to serve both compliance and operational needs without duplicating data at different sensitivity levels.

**Least-privilege for Collector credentials.** The Collector's backend credentials should be write-only. Read access is not required for data export and should not be granted. Separate the credential used by the Collector pipeline from credentials used by engineers querying the backend directly.

## Compliance Requirements Matrix

What each framework specifically requires of your telemetry pipeline:

| Requirement | GDPR | HIPAA | SOC 2 | PCI DSS |
|------------|------|-------|-------|---------|
| Data minimisation | Required (Art. 5) | Minimum necessary standard | Expected | Required |
| Encryption in transit | Expected | Required | Required | Required |
| Encryption at rest | Expected | Required | Expected | Required |
| Access logging | Required (RoPA) | Required | Required | Required |
| Retention limits | No longer than necessary | 6 years (medical records) | Policy-defined | 1 year minimum |
| Subject erasure rights | Required (Art. 17) | Not applicable | Not applicable | Not applicable |
| Audit trail | Required | Required | Required | Required |
| Data residency | EEA transfer restrictions | US-centric (HITECH) | Geography varies | Policy-defined |
| Sensitive data category | Personal data (broad) | PHI (defined list) | Customer data | Cardholder data (CHD) |

The most demanding intersection is a healthcare organisation handling EU residents: HIPAA's PHI controls combined with GDPR's erasure rights, in a context where standard log retention for incident response conflicts with both simultaneously.

<!-- TODO: Expand HIPAA section: what qualifies as PHI vs. non-PHI in telemetry (IP address, session ID, device ID, visit timestamps are PHI in combination), covered entity and business associate obligations, BAAs with telemetry vendors, minimum necessary standard applied to trace granularity -->
<!-- TODO: Expand SOC 2 section: Trust Service Criteria — CC6 logical access, CC7 system monitoring, CC2/CC3 change management. How telemetry data satisfies the monitoring evidence requirement for a Type II audit. -->
<!-- TODO: Expand PCI DSS section: cardholder data environment (CDE) scope and how telemetry from CDE systems is classified, network segmentation requirements for observability infrastructure that spans CDE and non-CDE zones -->
<!-- TODO: Audit trail implementation detail — tamper-evidence, append-only storage, integrity verification, querying audit records — covered in companion guide /guides/audit-trail-implementation/ when that guide is complete -->
<!-- TODO: Data sovereignty deep-dive — per-jurisdiction telemetry residency requirements (EU GDPR, China PIPL, India DPDPA, California CPRA) — covered in /guides/data-sovereignty-and-residency/ -->
