---
title: "OpenTelemetry Semantic Conventions as a Dashboard Interface"
date: 2026-06-16
draft: true
excerpt: "A reference mapping from OpenTelemetry semantic convention attributes to the dashboard panels they imply. Use this as the lookup table behind tag-driven dashboard generation — or as a checklist for what your instrumentation should emit before you build dashboards by hand."
readtime: 10
tags: ["OpenTelemetry", "Observability", "Grafana", "Collector"]
---

<!--
GUIDE: In-depth technical reference. This is the practitioner lookup table:
given a set of OTel span/resource attributes, what dashboard panels should
exist? Organised by attribute group (service identity, database, HTTP,
messaging, Kubernetes, runtime). Each section covers: what the attribute
signals, which panels it warrants, what queries back those panels
(PromQL/NRQL/etc.), and what the "missing" case looks like (what you lose
if this attribute isn't set).

This is the reference document the article links to. It should be bookmarkable
on its own — a practitioner should be able to open this and use it as a
checklist without having read the article first.

SECTIONS TO WRITE:

## Service Identity Attributes
Attributes: service.name, service.version, service.namespace, service.instance.id
Panels implied:
- Service overview: rate (requests/sec), error rate (%), latency (p50/p95/p99)
  — the RED metrics
- Version comparison: error rate by service.version (catches bad deploys)
- Instance health: per-instance latency/error distribution (catches hot pods)

Key point: service.name is the minimum. service.version + a version comparison
panel is what catches silent regressions on deploy.

## HTTP / RPC Attributes
Attributes: http.method, http.route, http.status_code, rpc.system, rpc.service,
rpc.method
Panels implied:
- Endpoint performance table: p99 latency + error rate grouped by http.route
- Status code distribution: breakdown of 2xx/3xx/4xx/5xx by route
- Top slow endpoints: sorted by p99, filtered to error_rate > 0

Key point: http.route (not http.url) is the right grouping key — URLs contain
IDs and query params that create infinite cardinality. http.route gives you
/users/{id} rather than /users/12345.

Note on RPC: rpc.system = "grpc" implies a gRPC dashboard with status code
breakdown using gRPC status codes (0=OK, 2=UNKNOWN, 14=UNAVAILABLE, etc.)
not HTTP codes.

## Database Attributes
Attributes: db.system, db.name, db.operation, db.sql.table, db.connection_string
Panels implied:
- Query latency by db.operation (SELECT vs INSERT vs UPDATE — wildly different
  latency profiles)
- Slow query tracker: top queries by p99 latency
- Connection pool saturation (if instrumented — db.pool.size, db.pool.checked_out)
- Error rate by db.name (catches when one database in a cluster is unhealthy)

Key point: db.statement should be sanitised before emission (replace literals
with ?). The dashboard can show the sanitised template. Include a note about
the OTel spec recommendation for sanitisation.

db.system values and what they imply:
- "postgresql" / "mysql" / "mariadb" → SQL dashboard, operation breakdown
- "redis" → key operation dashboard (GET/SET/DEL rate, latency, miss rate)
- "mongodb" → document operation dashboard
- "elasticsearch" → search latency, index size panels
- "cassandra" → CQL operation breakdown

## Messaging Attributes
Attributes: messaging.system, messaging.destination, messaging.operation,
messaging.kafka.consumer.group (Kafka-specific)
Panels implied:
- Consumer lag by messaging.destination (the critical panel for queue health)
- Message processing latency (time from publish to consume)
- Dead letter queue rate
- Throughput by destination (messages/sec)

Key point: messaging.operation = "receive" vs "process" is the distinction
between when the message was picked up and when it was handled. The gap
between them is processing time. Both should be instrumented.

## Kubernetes Resource Attributes
Attributes: k8s.pod.name, k8s.deployment.name, k8s.namespace.name,
k8s.node.name, k8s.container.name
Panels implied:
- Pod restart count (the canary for crashloop backoff)
- Resource saturation: CPU throttle rate, memory usage vs limit
- Pod scheduling events (new pods, evictions)
- Node pressure: disk, memory, PID pressure conditions

Key point: k8s.deployment.name is the right grouping level for most operational
dashboards. k8s.pod.name is useful for drill-down, not overview. If you group
by pod name at the top level, the dashboard becomes unreadable at any scale.

## Runtime Attributes
Attributes: process.runtime.name, process.runtime.version, telemetry.sdk.language
Panels implied:
- GC pause time / frequency (JVM, .NET, Go)
- Heap usage / live objects (JVM, .NET)
- Goroutine count (Go)
- Thread pool saturation (JVM thread pools, Python async event loop lag)
- Memory leak indicator: heap growth over time with flat request rate

These attributes are set automatically by most OTel SDKs. The corresponding
panels require the runtime metrics from the OTel runtime instrumentation
libraries (not the tracing SDK — these are separate).

## Cloud / Infrastructure Attributes
Attributes: cloud.provider, cloud.region, cloud.availability_zone,
host.name, host.type
Panels implied:
- Multi-region latency comparison
- AZ failure indicator: error rate grouped by cloud.availability_zone
- Instance type cost proxy (if you know the pricing for host.type values)

## The Minimum Viable Attribute Set
Write a section that answers: if I can only ensure one set of attributes on
every span, what's the highest-value set?

Recommendation:
- service.name (required for anything)
- service.version (required for deploy comparison)
- http.route or db.system or messaging.system (required to know WHAT the service does)
- deployment.environment (required to separate prod from staging in every panel)

Without deployment.environment, every dashboard query needs a manual env filter
or you'll mix prod and staging data silently.

## What Missing Attributes Look Like
A section on the failure mode: what happens to the dashboard when a key
attribute is absent.

- Missing http.route: latency panels collapse into one line; you lose the
  ability to see which endpoint is slow
- Missing service.version: deploy regression panels don't exist; you only find
  out something broke when the error rate spikes, not when you can still
  correlate it to the deploy
- Missing db.operation: all database calls look the same; a slow full-table
  scan looks identical to a fast indexed SELECT

This section is important because it connects the dashboard spec back to
instrumentation quality. The guide should end with: the dashboard is only as
good as the attributes. Fixing your dashboards often means fixing your spans.

FORMAT NOTES:
- Each major section should have a reference table: attribute → panel → query pattern
- Use insight boxes for "gotchas" (http.route vs http.url cardinality,
  sanitised db.statement, deployment.environment scope)
- Include at least one Mermaid diagram showing the attribute → panel dependency
  graph for the "minimum viable" case
- This is a reference guide — it's okay to be drier than the articles. Lists
  and tables are appropriate here.

CROSS-LINK TO:
- Article: content/articles/tag-driven-dashboards-why-yours-are-already-wrong.md
- How-to: content/howtos/generate-dashboard-from-otel-tags.md
-->
