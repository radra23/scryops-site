---
title: "Your Traces Are Leaking User Data"
date: 2026-05-26
draft: true
excerpt: "Every OTel span that includes a customer email, shipping address, or payment token is a GDPR audit waiting to happen. The fix isn't application code — it's a Collector pipeline."
readtime: 8
tags: ["OpenTelemetry", "Privacy", "GDPR", "Security", "Observability", "Collector"]
---

> "The data you collect to understand your system can, without care, become the data that defines your liability."
> — A Developer, One Week Before the GDPR Audit

Picture an engineer adding a helpful attribute to a `process_order` span: the customer's email, because it makes debugging so much easier. You can find all the traces for a given user. You can correlate a support ticket to a trace in seconds. It's genuinely useful. It's also, quietly, a GDPR violation — and it's been sitting in your trace backend, indexed and searchable, ever since.

Most teams don't put PII in spans intentionally. It ends up there because the instrumentation reaches for whatever context is available: the order object, the request body, the user session. The context that makes debugging easy and the context that identifies individuals are often the same thing. By the time anyone notices, there are months or years of personal data in a system that was never designed to be a personal data processor.

GDPR enforcement has resulted in significant fines — multi-million euro penalties — for inadequate technical controls around personal data, with no leniency for unintentional collection. The "we didn't know it was there" defence has been explicitly rejected in DPA rulings across the EU. The data is there. You own it. You're responsible for it.

## Where the Leaks Come From

The most common sources of PII in telemetry are also the most useful pieces of debugging context. That's not a coincidence.

**Span attributes** are the most frequent leak point. Instrumentation libraries that automatically capture HTTP request parameters, gRPC request/response bodies, or database query arguments will include whatever was in those payloads — a `user.login` span with the email as the username attribute, a `payment.process` span with the card token, an `address.validate` span with the full shipping address.

**Log records correlated to traces** carry the same risk. A structured log line that includes the user ID, email, or IP address, emitted within a traced request, will be exported alongside the trace with the same `trace_id`. Fixing the spans and ignoring the logs is only half a solution.

**Baggage propagation** is the sneakier one. If your application propagates user identity through W3C baggage headers — which some authentication middlewares do automatically — every downstream span in the distributed trace will contain that baggage, including spans in services that have no business knowing the user's identity.

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

The span is still useful for debugging. You can still correlate traces with orders via the hashed ID. You can still see the payment provider was Visa. You can still see the cart was three items totalling ~$250. What you cannot do is identify the customer, expose their address, or leak their payment token. The diagnostic value survives. The personal data doesn't make it through.

{{< insight lightbulb >}}
**The governing principle:** preserve *business observability* while removing *personal identifiability*. You can almost always replace PII with derived, non-identifying values that serve the same diagnostic purpose — a hashed order ID still lets you correlate; a raw email address never needed to be there.
{{< /insight >}}

## A Decision Framework for Every Field

Not all attributes need the same treatment. Applying maximum protection to everything is as much a problem as applying none — you'll lose diagnostic value you actually need. Here's how to think about each field type:

| Signal Type | Example | Sensitivity | Action | Retention |
|---|---|---|---|---|
| System identifier | Service name, pod ID | None | Keep as-is | Long-term |
| Business identifier | Order ID, transaction ID | Medium | Hash (correlatable) | Medium-term |
| Personal identifier | Email, phone, name | High | Remove or tokenise | Minimal |
| Location (specific) | Street address, postcode | High | Remove or coarsen to region | Minimal |
| Location (coarse) | Country, state | Low | Keep | Medium-term |
| Payment data | Card number, token | Critical | Remove entirely | None |
| Technical data | Latency, status code | None | Keep as-is | Long-term |

The "hash" treatment for business identifiers deserves explanation: you replace the raw value with a deterministic hash, which means you can still correlate across spans (all spans for `ORD-12345` share the same hash) without the hash being reversible to the original value. The order ID is useful for correlation; the actual number doesn't need to be stored.

One important caveat: this approach is safe for opaque business identifiers like order IDs or transaction IDs, where the value space is large and unpredictable. Do **not** apply unsalted SHA-256 to personal identifiers like email addresses — the value space of common email addresses is small enough to be exhausted by a pre-computed rainbow table in seconds. If you need a correlatable pseudonym for a user, use HMAC-SHA256 with a rotating secret key stored outside the telemetry system, or tokenise the value and discard the mapping from the pipeline entirely.

{{< mermaid >}}
flowchart TD
    A[Attribute in Span] --> B{Required for<br/>operational debugging?}
    B -->|Yes| C[System / Technical Data]
    B -->|No| D{Does it identify<br/>an individual?}
    C --> E[Keep as-is]
    D -->|No| F{Does it describe<br/>business context?}
    D -->|Yes| G{Can it be derived<br/>or anonymised?}
    F -->|Yes| H[Keep as-is]
    F -->|No| I[Remove]
    G -->|Yes| J[Hash or coarsen]
    G -->|No| K[Remove entirely]
{{< /mermaid >}}

Run every attribute in your instrumentation through this decision tree. The result is your PII handling policy — and it becomes your Collector transform configuration.

## The Fix Lives in the Collector, Not the Application

The right place to strip PII is the OTel Collector, not application code. Doing it in application code means every service team needs to remember to implement it correctly, consistently, and update it whenever new fields are added. One team forgets; you have a gap. One new service joins the platform; you have a gap.

The Collector's `transform` processor lets you define attribute-level operations that apply to all spans passing through the pipeline — regardless of which service emitted them. The `SHA256()` OTTL converter used below requires `otelcol-contrib` v0.96.0 or later.

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

          # Hash medium-sensitivity business IDs (SHA-256, truncated)
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
`error_mode: ignore` means the pipeline keeps processing even if a `delete_key` or `set` operation fails — for example, if a span doesn't have the expected attribute. Without it, a malformed span can block the entire pipeline. Always set it.
{{< /insight >}}

## What the Regulations Actually Require

GDPR's data minimisation principle (Article 5(1)(c)) requires that personal data be "adequate, relevant and limited to what is necessary." Telemetry data that includes customer emails, addresses, or payment tokens is almost never necessary for the purpose of system observability. A DPA audit that finds this data in your trace backend will find a violation regardless of your intent.

CCPA adds a right to deletion obligation: if a customer requests erasure, you need to be able to delete their data from all systems where it's stored. "All systems" includes your trace backend. If you hash at ingest and remove all other direct identifiers from the same spans, the mapping from customer identity to trace data doesn't exist in the backend — you've made the deletion problem disappear before it arrives. Any un-hashed PII field left in the same span — a shipping address alongside the hashed order ID, for example — would still require deletion handling.

HIPAA's minimum necessary standard applies the same logic to health data: use or disclose only the minimum amount of protected health information necessary. If you're instrumenting a healthcare application, any PHI in your telemetry is a potential HIPAA violation.

The Collector pipeline approach satisfies all three frameworks simultaneously: data that never enters the backend doesn't need to be deleted, minimised, or protected there.

## Where to Start

The migration from "PII everywhere" to "PII nowhere" doesn't require a big-bang effort. Start by auditing what's currently in your trace backend. Most backends support a simple attribute search — run queries for common field names (`email`, `phone`, `address`, `card`, `ssn`, `dob`) across a sample of recent traces. Build the list of fields that need treatment. Then implement the Collector transforms and verify the output against a known span.

The pipeline fix takes an afternoon. The regulatory exposure it removes has been known to take considerably longer.

Every span attribute that never enters the backend is one field that can't be subpoenaed, breached, or surfaced in a DPA audit.

For the specific transformation techniques — hashing, tokenisation, coarsening, and quality gates — see [Data Masking in Telemetry](/guides/data-masking-in-telemetry/).

{{< obs-mascot class="cleric" tag="guardian of the redaction pipeline" quip="I have blessed this span and cast out its sins — the email, the card, the home address. Go forth, telemetry, and leak no more. ...the redaction belongs in the Collector, not in prayer. Configure it there." >}}
