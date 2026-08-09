---
title: "Telemetry Compliance: Data Rights, Retention, and Access Controls"
date: 2026-06-11
draft: true
excerpt: "GDPR compliance in telemetry goes beyond stripping PII from spans. It requires managing data subject rights, enforcing retention schedules, and controlling who can query what. This guide covers the operational obligations."
readtime: 8
tags: ["Privacy", "GDPR", "Compliance", "Observability", "Security"]
---

Removing PII from spans is step one, not the finish line. GDPR keeps going after that: data subjects can request access to their data, demand erasure, or ask for a portable copy. Retention periods need to be set, enforced, and auditable. Access to sensitive telemetry needs to be restricted by role and data classification. That's what this guide covers. For the identification and transformation steps that come first, see [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) and [Data Masking in Telemetry](/guides/data-masking-in-telemetry/).

## The Governing Principles

GDPR Article 5 sets out six principles for personal data processing: lawfulness/fairness/transparency, purpose limitation, minimisation, accuracy, storage limitation, and integrity/confidentiality. Article 5(2) adds an accountability obligation on top. Here's the subset with direct consequences for a telemetry pipeline:

**Lawfulness & fairness**: collection needs a documented legal basis: consent, contract fulfilment, legitimate interest, or one of the Article 6 alternatives. "It's useful for debugging" is not a legal basis, and a basis that's technically defensible but doesn't match what a reasonable user would expect still fails the fairness test.

**Transparency**: data subjects need to know what's collected, why, and where it goes. If your telemetry pipeline processes personal data, your privacy notice has to say so.

**Purpose limitation**: data collected for one purpose (debugging, say) can't quietly get repurposed for another (marketing analytics) without a new legal basis. Being able to state that purpose per attribute is exactly what the Implementation Checklist, below, asks of you.

**Minimisation**: collect only what the stated purpose actually needs. Every attribute in a span should have an explicit reason to exist. Can't state the purpose? The field shouldn't be there.

**Storage limitation**: personal data can't stick around longer than the purpose requires. See Retention Lifecycle, below, for how that becomes a per-class retention schedule.

**Security** (integrity and confidentiality): apply technical measures that match the risk. Think access controls, encryption in transit and at rest, and audit logging on sensitive data access. "Appropriate" is calibrated to risk, not convenience.

Accuracy and accountability round out the six-plus-one. This guide doesn't give them their own section: accuracy shows up under Rectification (below), accountability lives in the Collection Notice Metadata register.

## Data Classification

Telemetry data falls into three broad classes, each requiring different handling:

{{< mermaid >}}
graph TD
    A[Telemetry Data] --> B[Personal Data]
    A --> C[Technical Data]
    A --> D[Business Data]
    B --> B1[Name]
    B --> B2[Email]
    B --> B3[Location]
    C --> C1[Metrics]
    C --> C2[Traces]
    C --> C3[Logs]
    D --> D1[Transaction IDs]
    D --> D2[Feature Usage]
    D --> D3[Business Events]
{{< /mermaid >}}

**Personal Data** can identify a person directly or indirectly, and it gets the strongest protection there is: strip or hash before export, shortest retention, most restrictive access.

**Technical Data** (metrics, traces, and logs about system behaviour) is typically not personal, unless it carries user-identifying attributes. Handle with care: confirm no PII is hiding in there before you call it non-personal.

**Business Data** (transaction IDs, feature usage, conversion events) powers analytics without identifying individuals, as long as business IDs are hashed and never cross-referenced to personal data in the same system.

## Data Rights Management

GDPR Articles 15–20 define six data subject rights over personal data. Four map cleanly onto telemetry pipeline mechanics: access, erasure, portability, and rectification. Your pipeline needs to be able to respond to all four. The other two matter less often for telemetry specifically, but don't ignore them: restriction of processing and a third-party notification obligation, both covered below.

{{< mermaid >}}
graph LR
    A[Data Subject Request] --> B{Request Type}
    B --> C[Access]
    B --> D[Erasure]
    B --> E[Portability]
    C --> F[Data Lookup]
    D --> G[Data Removal]
    E --> H[Data Export]
    F --> I[Response]
    G --> I
    H --> I
{{< /mermaid >}}

**Access (Article 15)**: the subject can request a copy of their personal data, plus information about how it's processed. Your telemetry backend needs to be queryable by a user-linked token or hashed identifier, so you can pull the relevant spans and logs.

**Erasure (Article 17)**: the "right to be forgotten." Any personal data in your telemetry that wasn't anonymised at ingest needs to be locatable and deletable on request, unless one of Article 17(3)'s exemptions applies. Those exemptions (a legal retention obligation, public-interest archiving or research, defence of legal claims) are rare for telemetry specifically, but check with legal before assuming erasure is always unconditional. This is exactly why hashing at the Collector and purging all direct identifiers beats trying to find and delete them later: if no direct identifier ever reaches the backend, there's nothing to erase.

**Portability (Article 20)**: where processing is based on consent or contract, subjects can request their data in a structured, machine-readable format. Telemetry data rarely shows up in a portability request, but if it does, you need an export path ready.

**Rectification (Article 16)**: inaccurate data has to be correctable. For most telemetry this is moot (historical spans are immutable), but for any user preference or consent data stored alongside telemetry, you need an update path.

**Restriction (Article 18)**: where a subject disputes the accuracy of their data, or objects to processing pending resolution, you need to suppress it from active use without deleting it. For telemetry this usually means flagging the record (or its hashed identifier) so normal query paths exclude it while retention and audit paths still keep it. Call it a soft delete, not the hard delete erasure requires.

**Third-party notification (Article 19)**: if you've shared telemetry containing personal data with a downstream processor (an analytics vendor, an external SRE contractor), any rectification, erasure, or restriction you apply needs to reach them too, unless that's impossible or disproportionate effort.

{{< insight >}}
Retention period enforcement is your best tool for limiting erasure exposure. Data that has already been deleted on schedule cannot be the subject of an erasure request.
{{< /insight >}}

## Retention Lifecycle

GDPR's storage limitation principle (Article 5(1)(e)) requires that personal data be kept no longer than necessary. Telemetry retention should be tiered by data classification:

{{< mermaid >}}
graph TD
    A[Data Collection] --> B[Active Use]
    B --> C[Archive]
    C --> D[Deletion]
    B --> E[Duration set per data class]
    C --> F[Duration set per data class]
    D --> G[Permanent erasure]
{{< /mermaid >}}

Not every class passes through every stage. Personal Data skips Archive entirely, moving straight from Active Use to Deletion. The specific periods depend on your legal basis and the operational purpose of the data. Here's a reasonable starting point for telemetry containing any personal attributes:

{{< obs-retention-timeline title="Retention by data class"
      units="days · solid = active window, hatched = archive, x = deletion"
      caption="Fig. — Personal data's retention window is a rounding error next to business and technical data, by design: the shortest possible active window and no archive tier at all. Personal (30d) and Technical (820d) are plotted at the upper bound of their stated ranges — see the table below for the full range." >}}
[ {"label":"Personal Data","self":30,"duration":30},
  {"label":"Business Data","self":90,"duration":455},
  {"label":"Technical Data","self":90,"duration":820} ]
{{< /obs-retention-timeline >}}

| Data Class | Active Retention | Archive | Deletion |
|---|---|---|---|
| Personal Data | 7–30 days | None (no archival of PII) | At end of active period |
| Business Data | 90 days | 1 year | At end of archive period |
| Technical Data | 90 days | 1–2 years | At end of archive period |

Retention policies are meaningless without automated enforcement. Most observability backends support per-index or per-stream retention rules, so configure them explicitly. Don't rely on manual deletion.

## Access Patterns

Access to telemetry should be role-restricted by data classification:

{{< mermaid >}}
graph TB
    A[Data Access] --> B[Public]
    A --> C[Restricted]
    A --> D[Sensitive]
    B --> B1[Aggregate metrics]
    B --> B2[Health endpoints]
    C --> C1[Traces]
    C --> C2[Error logs]
    D --> D1[Personal data — during retention window]
    D --> D2[Audit logs]
{{< /mermaid >}}

**Public**: aggregate metrics on system health and availability, exposed to all internal users. No personal data, so no access control needed beyond standard authentication.

**Restricted**: distributed traces and error logs, which may carry business identifiers and operational context. Engineering and SRE get access; marketing and non-technical roles don't.

**Sensitive**: any telemetry that still contains personal data during its retention window, plus audit logs of who accessed what. Only a data protection officer or designated data steward role gets in, and even those access events get logged.

## Implementation Checklist

Before considering a telemetry pipeline GDPR-compliant, verify each of the following:

| Requirement | What to check | Telemetry implementation |
|---|---|---|
| Purpose limitation | Can you state why each attribute is collected? | Remove fields with no documented operational purpose |
| Data minimisation | Are you collecting only what's necessary? | Audit span attributes for fields that outlived their purpose |
| Storage limitation | Is a retention schedule defined and enforced? | Configure backend retention rules per data class |
| Lawful basis | Can you point to the legal basis for each pipeline? | Maintain a data processing register per pipeline |
| User rights | Can you locate, export, and delete on request? | Verify lookup by hashed user ID works end-to-end |
| Security | Are access controls enforced by role? | Confirm backend RBAC rules match the three-tier model above |
| Transparency | Is the privacy notice current? | Verify it discloses telemetry data processing |

## Collection Notice Metadata

For each telemetry data collection point that handles personal data, maintain machine-readable metadata documenting the governance context. This doesn't live in spans; it lives in a data processing register alongside the pipeline definition:

```json
{
  "collection_notice": {
    "pipeline": "checkout_traces",
    "purpose": "system_monitoring",
    "retention_days": 30,
    "sharing": ["internal_sre"],
    "legal_basis": "legitimate_interest",
    "pii_present": false,
    "masking_applied": ["customer.email → removed", "order.id → SHA256"]
  }
}
```

`pii_present: false` should only get set after you've confirmed the masking pipeline actually ran. If the Collector transform configuration changes, update this register entry in the same change.

<!-- TODO: Add DPIA (Data Protection Impact Assessment) trigger criteria — when is a DPIA required for telemetry changes? -->
<!-- TODO: Add guidance on consent propagation — how user consent state flows from application to telemetry pipeline -->
<!-- TODO: Cover cross-border data transfer obligations (SCCs, adequacy decisions) if telemetry is exported to non-EU backends -->
<!-- TODO: Add audit log requirements for sensitive data access events -->

- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — identifying PII in telemetry and the Collector-based fix
- [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) — hashing, tokenisation, and transformation techniques
- [OTel Exporter Configuration](/guides/otel-exporter-configuration/) — where in the Collector pipeline to apply transform processors
