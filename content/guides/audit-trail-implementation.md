---
title: "Implementing Audit Trails with OpenTelemetry"
date: 2026-06-10
draft: false
excerpt: "An audit trail is not a log. It's a tamper-evident, time-ordered record of who did what, when, and why. Most teams build this wrong. Here is how to do it correctly using OpenTelemetry and append-only storage."
readtime: 8
tags: ["Compliance", "Security", "OpenTelemetry", "Logs", "Privacy"]
---

Most audit trails are just application logs with the word "audit" in the logger name. They're written by the same code path, into the same store, under the same retention policy, with the same write permissions.

That distinction matters exactly once, and by then it's too late: when someone asks whether a record could have been altered, and the honest answer is that anyone with database access could have changed it and nobody would know.

{{< obs-telemetry-controls-map here="access" >}}

## Audit Trail Versus Application Log

They look similar. They answer to very different requirements.

{{< obs-audit-vs-log >}}

An application log is a debugging aid. It's lossy by design: sampled, rate-limited, rotated, dropped under load. That's correct behaviour, because losing a log line during an incident costs you a little context.

An audit trail is evidence. Losing a record is a control failure. Altering one undetectably is a much worse control failure. And the threat model is different in a way that changes the architecture: an application log defends against confusion, while an audit trail defends against a person with legitimate access who wants a record to say something else.

Insider, not outsider. That single difference drives every design decision below.

## What the Frameworks Require

You'll find the requirement in all four frameworks covered in [Observability Under Compliance](/guides/compliance-observability/), just phrased four different ways.

**SOC 2** asks for it through CC6.1–CC6.8 (logical access) and CC7.2–CC7.3 (monitoring and evaluating events). What's actually tested is evidence: whether the control you described operated for the whole period and whether you can prove it.

**HIPAA** §164.312(b) requires audit controls: hardware, software or procedural mechanisms that record and examine activity in systems containing ePHI. Retention follows the six-year documentation rule at 45 CFR §164.316(b)(2)(i).

**PCI DSS** is the most explicit. Requirement 10.2 defines the events; 10.3 requires that logs be protected from modification; 10.5 restricts access to them; 10.7 sets retention at twelve months minimum with three months immediately available.

**GDPR** doesn't mandate an audit trail in those words, but Article 5(2) accountability and Article 30 records of processing both require you to demonstrate what you did with personal data. An access record is the usual way.

The union of those is a short specification: record actor, action, resource, outcome and time; keep it for six years; make modification detectable; restrict who can read it.

## The Properties

Four, and only the first is unusual.

**Tamper-evidence.** Why not tamper-*proof*? That's not achievable against an attacker with sufficient access, and claiming it invites a bad question. Tamper-evident means an alteration can be *detected*. This is the property that separates an audit trail from a log file, and it's cheaper to achieve than you'd think.

**Completeness.** Every in-scope event, with no sampling. An audit trail with a 10% sample rate isn't an audit trail. This has a direct consequence for OpenTelemetry: audit events must never pass through a tail-sampling processor, and must be routed through their own pipeline.

**Integrity of ordering.** Records must be reconstructible in the order they happened. Wall-clock timestamps from distributed hosts aren't enough on their own. Clock skew is real, and "these two records are one second apart" isn't a claim you want to defend. Sequence numbers per writer, or a hash chain, solve this properly.

**Availability over the retention period.** Six years is a long time for a storage format, a schema, and an access-control model. Whatever you build has to be readable by someone who wasn't there when you built it.

## Tamper-Evidence: How It Actually Works

So how do you actually get tamper-evidence? The mechanism is a hash chain, and it's four lines of code.

Each record includes the hash of the record before it:

```
entry_hash = H(timestamp ‖ actor ‖ action ‖ resource ‖ outcome ‖ previous_hash)
```

The first entry uses a fixed genesis constant. Every subsequent entry commits to the entire history that precedes it.

{{< obs-hash-chain >}}

The property this gives you is precise and worth stating precisely: **altering any past record invalidates every hash after it.** An attacker who edits record 400 must recompute records 401 through *n* to keep the chain consistent. If you've published or externally stored any hash after 400, whether that's a daily root, an offsite copy, or a printout in a drawer, that recomputation is detectable.

That last clause is the part most teams get wrong. A hash chain stored entirely inside the system it protects proves nothing against an attacker who can rewrite the whole store. The chain must be *anchored* somewhere the attacker doesn't control. Options, in ascending order of paranoia: write the daily root hash to a separate account's object storage with a WORM lock; email it to the compliance team; publish it to a transparency log.

### When a chain is not enough

A flat hash chain has one operational weakness: proving that a specific record is in the log requires walking the chain. That's O(*n*) in the number of entries, and at audit scale *n* is large.

Crosby and Wallach's 2009 work on tamper-evident logging is the standard reference here. Replacing the flat chain with a Merkle tree (a history tree over the entries) reduces both membership proofs and consistency proofs from linear to **logarithmic** in the number of entries.

{{< obs-proof-size >}}

The practical difference at audit scale is the difference between an answerable question and an unanswerable one. This is the same construction RFC 6962 uses for Certificate Transparency, which is a reasonable existence proof that it works at scale.

For most teams a flat chain plus daily anchoring is sufficient, and the honest recommendation is to start there. Reach for a Merkle tree when you need to hand an auditor a proof about a single record without handing them the entire log.

## What to Audit

Four categories. Anything outside them is an application log.

- **Authentication and authorisation events** — sign-ins, failures, privilege escalation, token issuance, session termination.
- **Data access** — reads of personal data, exports, bulk queries, and report generation. This is the category most teams omit and the one GDPR Article 30 is asking about.
- **Administrative operations** — user creation, role changes, permission grants, and anything an admin console can do.
- **Configuration changes** — including, pointedly, changes to the audit configuration itself and to the redaction rules in your telemetry pipeline. A change to a compliance control is an auditable event.

Queries against the observability stack belong in the second category. Both SOC 2 CC6 and PCI 10.5 ask who can read your telemetry, and most teams can't answer for their trace backend.

## Modelling Audit Events in OpenTelemetry

An audit event is a span with a mandated attribute set, or a log record with the same. Spans are the better fit when the audited operation already has one. You get causality and duration for free.

The attribute set is a five-tuple plus context:

```yaml
audit.actor.id:        "usr_8f2c"        # tokenised, never a raw email
audit.actor.type:      "user"            # user | service | system
audit.action:          "data.export"     # verb, from a closed vocabulary
audit.resource.type:   "customer_record"
audit.resource.id:     "cus_3a91"        # tokenised
audit.outcome:         "success"         # success | failure | denied
audit.reason:          "dsar_fulfilment" # why, where a purpose applies
audit.sequence:        184203            # monotonic per writer
audit.prev_hash:       "9f2c…"           # the chain
```

Three notes on this.

`audit.action` should come from a **closed vocabulary** defined in one place. Free-text action names make the trail unqueryable within about six months, and "unqueryable" and "non-compliant" converge under audit.

The actor and resource identifiers are **tokenised**, not raw. An audit trail is itself a personal data store. It records what a named person did, and it's retained for six years under a mandate that overrides your minimisation ceiling. GDPR Article 17(3)(b) is what makes that lawful: erasure doesn't apply where processing is necessary for compliance with a legal obligation. Tokenising keeps the record useful and the exposure small.

`audit.reason` is the field that turns a log into a defence. "Who accessed this record" is answerable from any log. "Why were they entitled to" is the question a regulator actually asks.

### Pipeline separation

The critical configuration detail: **audit events must not share a pipeline with application telemetry.**

```yaml
service:
  pipelines:
    logs/audit:
      receivers:  [otlp/audit]
      processors: [batch]            # no sampling, no filtering
      exporters:  [audit_store]
    logs/app:
      receivers:  [otlp]
      processors: [transform/redact, probabilistic_sampler, batch]
      exporters:  [otlp/backend]
```

Any processor that can drop a record (samplers, filters, rate limiters) breaks completeness. A redaction processor on the audit pipeline is worse than useless: it'll strip the actor identifier that the record exists to preserve.

This is also why the [PII redaction rules](/guides/pii-in-telemetry/) must be scoped to the application pipeline rather than applied globally. The two pipelines want opposite things.

## Storage

The requirement is append-only, and it's met at the storage layer rather than in application code. Anything enforced only by your service can be bypassed by anyone who can reach the database directly. That's precisely the threat model.

Three workable options:

- **Object storage with an object-lock retention policy**, in compliance mode, in a separate account with separate credentials. Cheap, durable, and the retention is enforced by the provider rather than by your code.
- **A managed audit service** such as a cloud provider's own trail product, for infrastructure-plane events. Good coverage of the infrastructure, no coverage of your application's data access.
- **An append-only log store** with immutability configured, for the queryable tier, usually alongside one of the above rather than instead of it.

The pattern most teams end up with is tiered: hot and queryable for the first ninety days, warm for twelve months, cold and archival to six years. That maps onto PCI's three-month immediate-availability requirement and HIPAA's six-year documentation rule without paying hot-storage prices for either.

Separate credentials for the audit store aren't optional. If the same role that can write application telemetry can also write or delete audit records, the tamper-evidence is decorative.

## Alerting

An audit trail nobody reads is a storage bill with compliance branding. Four alerts justify their own noise:

- **Chain verification failure** — the daily integrity check found a break. Page someone.
- **A gap in the sequence** — records 1000 and 1002 with no 1001. Either a bug or a deletion.
- **Volume anomalies** — a bulk export at 03:00, or an actor reading a hundred times their weekly average.
- **Audit pipeline silence** — no audit events for longer than expected. The most common real failure isn't tampering; it's the exporter quietly failing and nobody noticing for a month.

That last one catches more incidents than the other three combined.

## Testing It

Four tests, and the third is the one nobody writes.

1. **Completeness** — perform each in-scope operation in a test environment and assert a corresponding record arrives. This is the test that catches a new endpoint shipping without audit coverage.
2. **Chain integrity** — verify the full chain on a schedule, not only on demand. A break discovered during an audit is a much worse day than one discovered on a Tuesday.
3. **Tamper detection** — deliberately modify a record in a copy of the store and assert that verification fails. An untested detection control is an assumption.
4. **Retrieval at age** — restore and read a record from the oldest tier. Six-year retention that nobody has ever read back is a hypothesis.

{{< insight bookmark >}}
The failure mode of an audit trail is silence. It does not crash, page anyone, or show up on a dashboard — it simply stops receiving events, or starts accepting records that cannot be verified, and stays that way until an auditor asks. Alert on the absence of audit events with the same seriousness you alert on error rates.
{{< /insight >}}

{{< obs-mascot class="ranger" quip="I have tracked every actor, action and resource through six years of undergrowth. The chain holds. Do not ask me to do it again without an index." >}}

## See Also

- [Observability Under Compliance](/guides/compliance-observability/) — the four frameworks and where audit trails sit in each
- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — why the redaction pipeline must not touch the audit pipeline
- [Telemetry Data Sovereignty](/guides/data-sovereignty-and-residency/) — audit records are personal data, and they have a jurisdiction
- [Scrub PII from Application Logs in .NET](/howtos/scrub-pii-from-application-logs-dotnet/) — the `PIIAccessAuditLogger` pattern in application code
