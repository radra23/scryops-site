---
title: "Observability Under Compliance: GDPR, HIPAA, SOC 2, and PCI DSS"
date: 2026-06-10
draft: false
excerpt: "Regulated industries need observability too. A guide to building telemetry pipelines that satisfy GDPR, HIPAA, SOC 2, and PCI DSS requirements — covering data minimisation, retention mandates, audit trails, and what each framework actually requires."
readtime: 10
tags: ["Compliance", "Privacy", "GDPR", "Security", "Observability"]
---

Four frameworks, four vocabularies, one pipeline. GDPR calls it a lawful basis. HIPAA calls it minimum necessary. SOC 2 calls it a Trust Services Criterion. PCI DSS calls it Requirement 10. They are asking your telemetry pipeline different questions, and the answers are mostly the same six or seven engineering decisions.

This guide is about those decisions. For the mechanics of getting PII out of spans, start with [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/); for the transformation techniques, [Data Masking in Telemetry](/guides/data-masking-in-telemetry/).

{{< obs-telemetry-controls-map here="collector" >}}

## The Tension

Every compliance conversation about observability runs into the same contradiction, and it is worth stating plainly before the frameworks pile up.

You need data to debug. You need to delete data to comply.

Both halves are real. An incident at 03:00 is easier to resolve with a week of high-cardinality traces than with an hour of aggregates. A regulator asking why you still hold a deleted user's session data does not care that the traces were useful.

What makes this tractable is that the two pressures act on *different data*. Diagnostic value lives in structure: which service called which, how long it took, what failed. Compliance risk lives in identity: who it was. Those are separable, and most of the work in a compliant telemetry pipeline is separating them early enough that the rest of the system never has to choose.

{{< obs-compliance-tension >}}

The retention picture is where the contradiction gets sharpest, because here the frameworks disagree with each other rather than with you.

{{< obs-retention-ladder >}}

PCI DSS Requirement 10.5.1 sets a floor: at least twelve months of audit log history, with the most recent three months immediately available for analysis. HIPAA's documentation retention under 45 CFR §164.316(b)(2)(i) runs six years, and audit records are generally kept within that scope. SOX pushes some financial-system records to seven.

GDPR sets no floor at all. Article 5(1)(e) sets a *ceiling*: personal data must be kept no longer than is necessary for the purposes it was collected for.

A single retention policy can't satisfy both a six-year mandate and a minimisation ceiling, unless the data being retained for six years contains no personal data. That's the whole trick, and it's why the field-level decisions in the [PII guide](/guides/pii-in-telemetry/) come before the retention policy rather than after it. Strip identity at ingest, and the long-retention obligation applies to records that carry no erasure obligation. Keep identity, and every framework's retention floor becomes a GDPR liability with a clock on it.

## What Each Framework Actually Asks

{{< obs-compliance-matrix >}}

### GDPR

Four articles do most of the work.

**Article 6 — lawful basis.** You need one for telemetry, and it's almost always legitimate interests under Article 6(1)(f) rather than consent. Nobody consents to being traced. Legitimate interests requires a balancing test you can produce on request: what the processing achieves, why it's necessary, and why it doesn't override the data subject's rights. Write it down once. Auditors ask for the document, not the reasoning.

**Article 5(1)(c) — data minimisation.** Personal data must be adequate, relevant and limited to what is necessary. This is the article a raw email address in a span attribute fails, and it fails on its own terms: the stated purpose is diagnosis, and diagnosis never needed the email.

**Article 17 — right to erasure.** One month to respond. If your trace backend retains spans for longer than that and those spans carry identifiers, a request landing today reaches data you emitted before it arrived. Hashing identifiers at ingest isn't a compliance dodge here; it's the difference between a deletion job that has to run across a trace store and one that doesn't exist.

**Article 25 — data protection by design and by default.** The one people skip. It requires that protective measures be built into processing from the outset rather than applied afterwards. A Collector pipeline that strips PII before export is an Article 25 control. A quarterly script that deletes it later isn't, and an auditor who knows the difference will say so.

### HIPAA

HIPAA's Security Rule asks for two things from telemetry specifically. §164.312(b) requires audit controls: mechanisms that record and examine activity in systems containing electronic protected health information. §164.502(b) applies the minimum necessary standard to uses and disclosures.

The trap is the 18 identifiers under §164.514(b)(2). Four of them appear in essentially every span your instrumentation produces by default: dates, IP addresses, device identifiers, and URLs. A trace from a healthcare application that records a request timestamp, the client IP, and the URL path is holding three of the eighteen without anyone having decided to.

Note also that the OCR guidance most commonly cited here, the December 2022 bulletin on online tracking technologies updated March 2024, was vacated by the Northern District of Texas in June 2024. The underlying duty is unchanged; the guidance document isn't currently operative. Cite the regulation, not the bulletin.

### SOC 2

SOC 2 is the odd one out: it's an attestation against controls you define, not a rulebook you comply with. That makes it easier to pass and easier to fail for procedural reasons.

The Trust Services Criteria that touch observability directly are CC6.1 through CC6.8 (logical access), CC7.2 (monitoring for anomalies), and CC7.3 (evaluating security events). What auditors test isn't whether you have telemetry. It's whether the control you *described* operated for the whole period, and whether you can prove it.

{{< obs-soc2-exceptions >}}

The pattern in reported exceptions is consistent and slightly deflating: the failures are administrative, not technical. Access reviews that were scheduled quarterly and happened twice. Terminated users whose access lingered for days. Log monitoring that was configured but where nobody could produce evidence that anyone reviewed the output. Backup restoration that was never tested.

For telemetry, that translates to a specific piece of advice. If you claim in your system description that you review access to observability tooling, the review has to leave a trace: a dated artefact with a name on it. An auditor can't test a habit.

{{< obs-auditor-asks >}}

### PCI DSS

PCI DSS is the most prescriptive of the four and, for telemetry, the easiest to reason about.

Requirement 3.5.1 prohibits storing the full primary account number in retrievable form beyond what is necessary; masked display (Requirement 3.4.1) is limited to the first six and last four digits. Requirement 3.3.1 prohibits storing sensitive authentication data after authorisation, full stop: CVV, full track data, PIN. There is no retention window for a CVV. There is no masking that makes it acceptable.

Requirement 10 covers logging: 10.2.1 defines what must be logged, 10.3.2 protects logs from modification, 10.3.1 requires access to be limited, and 10.5.1 sets the twelve-month retention floor with three months immediately available.

The practical consequence for an observability pipeline is scope. If cardholder data can reach your telemetry, your telemetry infrastructure is in the cardholder data environment, and everything in Requirement 10 applies to your trace backend, your log store, and the people who can query them. Keeping PANs out of spans isn't only a data-protection control. It's a scope-reduction control, and scope reduction is the cheapest compliance work there is.

{{< insight bookmark >}}
The four frameworks converge on one architectural decision: strip identity at the Collector, before export. GDPR gets minimisation by design, HIPAA gets minimum necessary, PCI gets scope reduction, and SOC 2 gets a control you can point an auditor at. One pipeline, four boxes ticked, and no per-service code to keep in sync.
{{< /insight >}}

## The Controls That Do the Work

Six controls cover the overlap between all four frameworks. None of them are exotic.

**1. Redact at the Collector, not in services.** A `transform` processor with OTTL statements runs once, applies uniformly, and is a single artefact to show an auditor. Per-service scrubbing drifts the moment one team ships without it. The Collector pipeline in the [PII guide](/guides/pii-in-telemetry/) is the reference implementation.

**2. Hash business identifiers, delete personal ones.** Order IDs and transaction IDs hashed with a salt stay correlatable and stop being personal data in most readings. Email addresses don't survive hashing: the value space is small enough to exhaust. So they get deleted. See [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) for where that line falls.

**3. Tier retention by content, not by signal type.** Traces stripped of identity can sit in cold storage for six years without a GDPR problem. Traces that carry identifiers shouldn't outlive the erasure deadline. Splitting the pipeline on that axis is more useful than splitting it on logs-versus-traces.

**4. Restrict and record access to telemetry.** Both SOC 2 CC6 and PCI 10.3.1 ask who can read your observability data. Most teams can't answer for their trace backend. This is also the cheapest audit finding to prevent: see [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/).

**5. Document the lawful basis and the field decisions.** A one-page table of every span attribute and its disposition satisfies Article 30 record-keeping, gives the SOC 2 auditor a control description, and, more usefully, tells the next engineer what to do with a new field.

**6. Keep the pipeline config in version control with review.** A change to a redaction rule is a change to a compliance control. SOC 2 change-management criteria apply to it whether or not you thought of it that way.

## Where the Frameworks Disagree

Three places, worth knowing before someone points them out in a review.

**Retention floors versus minimisation ceilings.** Covered above. Resolved by making long-retention data non-personal.

**Audit trails versus erasure.** An audit record proving that user X's data was deleted necessarily names user X. GDPR Article 17(3)(b) provides the exit: erasure doesn't apply where processing is necessary for compliance with a legal obligation. Retention of the audit record is that obligation. Keep the record; tokenise the subject identifier inside it.

**Cross-border transfer versus centralised observability.** A single global trace backend is operationally ideal and, for EU personal data, a transfer question. That one is large enough to have its own guide: see [Telemetry Data Sovereignty](/guides/data-sovereignty-and-residency/).

## Where to Start

In order, because the order matters:

1. Inventory the attribute keys your backend has actually seen in the last 24 hours. Not the ones your code intends to send. The ones that arrived.
2. Classify each as system, business, personal, or prohibited. Four buckets, one afternoon.
3. Write the Collector transform for the last two buckets and deploy it.
4. Split retention on the resulting boundary.
5. Write down what you did. That document is the control description for every framework above.

Step 1 is where most of the surprises live, and it's the step teams skip because they assume they know what their instrumentation sends. They rarely do.

{{< obs-mascot class="paladin" quip="Four frameworks, one pipeline, zero excuses. I have read all the criteria so you do not have to. Mostly." >}}

## See Also

- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — the Collector pipeline that implements most of the controls above
- [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) — hashing, tokenisation, coarsening, and which to use when
- [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) — the access-recording control for SOC 2 CC6 and PCI 10.3.1
- [Telemetry Data Sovereignty](/guides/data-sovereignty-and-residency/) — where telemetry may legally live
- [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/) — the application-level layer
