---
title: "Designing Logs for AI Analysis: Structure, Cardinality, and Feature Richness"
date: 2026-06-11
draft: true
excerpt: "Logs that humans can read are not automatically logs that ML models can learn from. Designing for AI analysis means choosing the right field types, avoiding high-cardinality traps, and emitting context that enables feature extraction without post-hoc enrichment."
readtime: 8
tags: ["Logs", "Structured Logging", "AI", "Observability"]
---

<!-- TODO: Draft this guide -->
<!--
Source material: "AI-Friendly Logging Examples: Intelligence in Action" — provides the
conceptual direction (rich context, business correlation, ML feature vectors) but all
C# code examples are fictional (invented utility methods, not OTel .NET SDK patterns).
Do NOT use the code from this source. Source code must come from OTel .NET SDK patterns
consistent with existing guides (Meter.CreateCounter<T>(), ActivitySource.StartActivity(),
ILogger with structured templates).

Sections to cover:
1. What makes a log AI-ready vs human-readable — the difference between a text search
   target and a feature matrix; structured fields as dimensions for ML models
2. Field type discipline — use consistent types per field (always numeric, always enum
   string, never mixed); why stringly-typed enums kill ML models
3. Cardinality strategy for ML — high-cardinality identifiers (trace_id, user_id) are
   good as join keys but should not be used as feature dimensions; categorical fields
   should have bounded value sets
4. Context at emission time — attributes that enable downstream analysis must be written
   at the point of the event; you cannot retroactively add user.tier to a log entry
5. Business context fields — mapping technical operations to business semantics
   (order.id, payment.provider, user.tier, product.category) using OTel resource
   attributes and span attributes, not custom fluent builders
6. OTel semantic conventions as the AI-ready baseline — standard attribute names
   (http.method, db.system, messaging.system) are the shared vocabulary that enables
   cross-service ML features without per-service schema mapping
7. What to exclude — PII, secrets, free-text fields with unbounded values; these are
   noise for ML models and compliance risks
8. Example: enriched HTTP request span with business context using OTel .NET SDK
   (ActivitySource.StartActivity + SetTag for categorical attributes)

Do NOT write:
- Methods like AssessBusinessSignificance(), GetCompetitiveBenchmark(), PredictRetentionImpact()
- The IMetricLogger fluent builder pattern
- Fictional ML scoring methods attached to logger calls
- The phased implementation roadmap or Slack channel references from the source
-->
