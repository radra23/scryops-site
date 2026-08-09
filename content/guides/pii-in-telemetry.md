---
title: "Your Traces Are Leaking User Data"
date: 2026-05-26
draft: false
excerpt: "Every OTel span that includes a customer email, shipping address, or payment token is a GDPR audit waiting to happen. The fix isn't application code; it's a Collector pipeline."
readtime: 8
tags: ["OpenTelemetry", "Privacy", "GDPR", "Security", "Observability", "Collector"]
---

> "The data you collect to understand your system can, without care, become the data that defines your liability."
> — A Developer, One Week Before the GDPR Audit

Imagine an engineer, eager to help, adding a customer's email to a `process_order` span. Debugging just got much easier: now you can find every trace for a user, match support tickets to traces in a snap, and generally feel like a troubleshooting wizard. Super handy. Also, quietly, a GDPR violation that's been lounging in your trace backend, indexed and ready for search, ever since.

Most teams don't purposely put personal data in spans. It gets there because the tools grab whatever information is available: the order details, the request content, the user session. The info that helps with debugging and the info that identifies people are often the same. By the time anyone realizes, there are months or years of personal data in a system that was never meant to handle personal data.

{{< obs-pii-stats >}}

GDPR regulators have given out huge fines for careless handling of personal data. We’re talking multi-million euro penalties, and they don’t care if you collected it by mistake. The old 'we didn’t know it was there' excuse? That gets laughed out of DPA hearings across the EU. If the data is in your system, it’s officially your problem to own and protect.

{{< obs-pii-hall-of-shame >}}

## Where the Leaks Come From

Here’s the main point: the most useful debugging details are exactly where personal data tends to sneak into your telemetry. This is not a coincidence.

**Span attributes** are the most frequent leak point. Instrumentation libraries that automatically capture HTTP request parameters, gRPC request/response data, or database query info will include whatever was in those messages: a `user.login` span with the email as the username, a `payment.process` span with the card token, an `address.validate` span with the full shipping address.

**Log records linked to traces** have the same risk. A structured log entry that includes the user ID, email, or IP address, created during a traced request, will be sent along with the trace using the same `trace_id`. Fixing the spans but ignoring the logs only solves part of the problem.

**Baggage propagation** is the trickiest. If your app passes user identity through W3C baggage headers (which some login middlewares do automatically), every later span in the trace will carry that baggage, even in services that shouldn't know the user's identity.

{{< obs-pii-leak-paths >}}

Three different routes, all ending in the same traffic jam. Baggage is the real troublemaker here. It doesn’t just drop PII into your backend; it spreads it across every downstream service’s spans, sometimes appearing in places that never even had the original data.

## The Crime Scene and the Clean Version

Here's what a real `process_order` span looks like before any PII handling:

```json
{
  "name": "process_order",
  "trace_id": "abc123def456789",
  "span_id": "def456abc123",
  "attributes": {
    "order.id": "ORD-12345",
    "customer.email": "alex.smith@example.com",
    "shipping.address": "123 Main St, San Francisco, CA 94105",
    "payment.token": "tok_visa_4242424242424242",
    "cart.items": [
      {"id": "PROD-001", "quantity": 2},
      {"id": "PROD-002", "quantity": 1}
    ]
  }
}
```

{{< obs-pii-redaction >}}

And the same span after a properly configured OTel Collector transform pipeline:

```json
{
  "name": "process_order",
  "trace_id": "abc123def456789",
  "span_id": "def456abc123",
  "attributes": {
    "order.id": "b3d9f1a2c4e5",
    "customer.region": "US-WEST",
    "payment.provider": "visa",
    "cart.item_count": 3,
    "cart.total_value_usd": 249.98
  }
}
```

The span still pulls its weight for debugging. You can match traces to orders with the hashed ID, see that Visa handled the payment, and know the cart had three items worth about $250. What you can’t do is identify the customer, reveal their address, or let a payment token slip out. The useful details stay, and the personal data gets bounced at the door.

{{< insight lightbulb >}}
**The governing principle:** preserve *business observability* while removing *personal identification*. You can almost always swap personal data with created, non-identifying values that serve the same diagnostic purpose. A hashed order ID still lets you connect data; a raw email address was never necessary.
{{< /insight >}}

## A Decision Framework for Every Field

Not every attribute needs to be locked up like it’s the crown jewels. If you lock everything down, you lose the diagnostic gold that actually helps you fix things. Here’s a quick cheat sheet for sizing up each field:

{{< obs-pii-blindspot >}}

| Signal Type | Example | Sensitivity | Action | Retention |
| --- | --- | --- | --- | --- |
| System identifier | Service name, pod ID | None | Keep as-is | Long-term |
| Business identifier | Order ID, transaction ID | Medium | Hash (correlatable) | Medium-term |
| Personal identifier | Email, phone, name | High | Remove or tokenise | Minimal |
| Location (specific) | Street address, postcode | High | Remove or coarsen to region | Minimal |
| Location (coarse) | Country, state | Low | Keep | Medium-term |
| Payment data | Card number, token | Critical | Remove entirely | None |
| Technical data | Latency, status code | None | Keep as-is | Long-term |

Let’s talk about hashing business identifiers. You trade the raw value for a deterministic hash, so every span for `ORD-12345` gets the same hash, but nobody can reverse-engineer the original order number. You can still link data, but the sensitive details stay hidden.

One important caveat: this approach is safe for opaque business IDs like order or transaction IDs, where the possible values are many and hard to guess. Do **not** use plain SHA-256 on personal data like email addresses; common emails can be cracked quickly using pre-made tables. If you need a linkable fake ID for a user, use HMAC-SHA256 with a changing secret key stored outside the telemetry system, or tokenize the value and discard the mapping from the pipeline completely.

{{< obs-pii-triage >}}

Run every attribute in your instrumentation through this decision tree. That’s your PII policy, ready to plug straight into your Collector transform config.

## The Fix Lives in the Collector, Not the Application

The best place to remove personal data is in the OTel Collector, not in your application code. Try to do it in the app, and suddenly every service team has to remember the rules, keep things consistent, and update every time a new field sneaks in. If one team forgets, you have a problem. If a new service joins, there’s a gap.

The Collector's `transform` processor lets you set up attribute-level rules that apply to every span moving through the pipeline, no matter which service sent it. The `SHA256()` OTTL converter in the example below needs `otelcol-contrib` v0.96.0 or later.

```yaml
processors:
  transform:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          # Remove high-sensitivity fields entirely
          - delete_key(attributes, "customer.email")
          - delete_key(attributes, "customer.phone")
          - delete_key(attributes, "shipping.address")
          - delete_key(attributes, "payment.token")
          - delete_key(attributes, "payment.card_number")

          # Hash medium-sensitivity business IDs (SHA-256)
          - set(attributes["order.id"], SHA256(attributes["order.id"])) where attributes["order.id"] != nil
          - set(attributes["customer.id"], SHA256(attributes["customer.id"])) where attributes["customer.id"] != nil

          # Coarsen location to region
          - set(attributes["customer.region"],
              attributes["shipping.country"])
              where attributes["shipping.country"] != nil
          - delete_key(attributes, "shipping.country")
          - delete_key(attributes, "shipping.city")

  # Logs need the same treatment
  transform/logs:
    error_mode: ignore
    log_statements:
      - context: log
        statements:
          - delete_key(attributes, "user.email")
          - delete_key(attributes, "user.ip_address")

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [transform, batch]
      exporters: [otlp/backend]
    logs:
      receivers: [otlp]
      processors: [transform/logs, batch]
      exporters: [otlp/backend]
```

{{< insight bookmark >}}
`error_mode: ignore` tells the pipeline to keep working even if a `delete_key` or `set` action fails. For example, if a span is missing an expected attribute, the pipeline won’t stop. Without this setting, a single malformed span could block everything. Always enable it.
{{< /insight >}}

## What the Regulations Actually Require

GDPR's data minimization rule (Article 5(1)(c)) requires that personal data must be "adequate, relevant and limited to what is necessary." Telemetry data with customer emails, addresses, or payment tokens is rarely needed for system observability. A DPA audit that finds this data in your trace backend will see it as a violation no matter your intent.

CCPA adds a right to deletion rule: if a customer asks to erase their data, you must delete it from all systems where it’s stored. "All systems" includes your trace backend. If you hash data when it enters and remove all other direct identifiers from the same spans, the link between customer identity and trace data doesn’t exist in the backend. You’ve solved the deletion problem before it starts. Any unhashed personal data left in the same span, like a shipping address with the hashed order ID, would still need deletion.

HIPAA's minimum necessary standard applies the same logic to health data: use or share only the smallest amount of protected health information needed. If you’re monitoring a healthcare app, any PHI in your telemetry could be a HIPAA violation.

{{< obs-pii-regimes >}}

The Collector pipeline approach checks all three boxes at once. Data that never enters the backend doesn't need to be deleted, minimized, or guarded there.

## Where to Start

{{< obs-pii-bingo >}}

Moving from 'PII everywhere' to 'PII nowhere' doesn’t have to be a massive project. Start by looking through your trace backend. Most backends let you search for attributes, so run a few quick searches for the usual suspects: `email`, `phone`, `address`, `card`, `ssn`, or `dob` in recent traces. Make a list of fields to fix. Then apply the Collector transforms and check the results against a known span.

The pipeline fix is an afternoon’s work. The regulatory headaches it saves you from will last for years.

Every span attribute you keep out of the backend is one less field that can be subpoenaed, breached, or flagged in a DPA audit. That’s peace of mind you can actually count.

For the specific transformation techniques — hashing, tokenization, coarsening, and quality gates — see [Data Masking in Telemetry](/guides/data-masking-in-telemetry/).

## See Also

- [Protecting Privacy in Software Logs: What Should Be Anonymized?](https://arxiv.org/abs/2409.11313) — Aghili, Li & Khomh, PACMSE / FSE 2025. The peer-reviewed source behind the opener stats and the blind-spot chart: 25 public log datasets, 58 papers, 45 practitioners surveyed.
- [DPC announces €91 million fine of Meta](https://www.dataprotection.ie/en/news-media/press-releases/DPC-announces-91-million-fine-of-Meta) — Irish Data Protection Commission, 27 September 2024. The decision behind the hall-of-shame figure's headline number.
- [Facebook Stored Hundreds of Millions of User Passwords in Plain Text for Years](https://krebsonsecurity.com/2019/03/facebook-stored-hundreds-of-millions-of-user-passwords-in-plain-text-for-years/) — KrebsOnSecurity, 21 March 2019. The original reporting, five years ahead of the DPC's decision.
- [American Hospital Assn. v. Becerra: Are Tracking Tools OK Again?](https://www.hklaw.com/en/insights/publications/2024/06/american-hospital-assn-v-becerra-are-tracking-tools-ok-again) — Holland & Knight, June 2024. Why this guide calls the HHS OCR tracking bulletin "contested" rather than live guidance.
- [CJEU — C-582/14 — Breyer](https://gdprhub.eu/index.php?title=CJEU_-_C-582/14_-_Patrick_Breyer) — GDPRhub case summary. The ruling that put a dynamic IP address in scope as personal data.
- [2025 Telemetry & Observability Report](https://www.sawmills.ai/observability-report-2025) — Sawmills, 2025. Vendor-run survey; source of the "13% of telemetry actively used" figure, labeled directional above.

{{< obs-mascot class="cleric" tag="guardian of the redaction pipeline" quip="I have blessed this span and cast out its sins — the email, the card, the home address. Go forth, telemetry, and leak no more. ...the redaction belongs in the Collector, not in prayer. Configure it there." >}}
