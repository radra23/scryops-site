---
title: "OTel Semantic Conventions: The Standard Dictionary for Telemetry Attributes"
date: 2026-06-10
draft: true
excerpt: "Every team that invents its own attribute names creates a system only they can query. OpenTelemetry semantic conventions are the shared vocabulary that makes cross-service queries, dashboards, and alerts work without per-team configuration. Here is what they cover and how to use them."
readtime: 9
tags: ["OpenTelemetry", "Observability", "Best Practices", "Tracing"]
---

Imagine trying to correlate HTTP errors across fifty services where one team uses `http.status`, another uses `status_code`, another uses `response.status_code`, and a fourth embeds the status in a log message with no structured field at all. This is not a hypothetical. It is the default state of an organisation that has not adopted semantic conventions.

OpenTelemetry semantic conventions are a specification — a standard dictionary of attribute names, their expected types, and their allowed values. When every service uses the same names for the same concepts, a single query covers the entire organisation.

## The Stability Tiers

Conventions are marked with a stability level. Before using one in production:

- **Stable** — safe to use; breaking changes require a major version bump
- **Experimental** — may change; use with awareness that attribute names could shift
- **Deprecated** — replaced by another convention; migrate when feasible

The [OpenTelemetry specification repository](https://opentelemetry.io/docs/specs/semconv/) is the canonical source of truth.

## HTTP Spans

The most widely used conventions. For an inbound HTTP request handled by a server:

```
http.request.method     "GET" | "POST" | "PUT" | "DELETE" | ...
url.full                "https://api.example.com/v1/orders?page=2"
url.path                "/v1/orders"
url.scheme              "https"
server.address          "api.example.com"
server.port             443
http.response.status_code  200
http.route              "/v1/orders"          # the template, not the specific path
network.protocol.version   "1.1" | "2"
user_agent.original     "Mozilla/5.0 ..."
```

For an outbound HTTP request made by a client:

```
http.request.method     "GET"
url.full                "https://stripe.com/v1/charges"
server.address          "stripe.com"
server.port             443
http.response.status_code  200
```

**Note on status codes:** Set span status to `ERROR` for 5xx responses. Do not set `ERROR` for 4xx — they are valid responses, not system failures.

## Database Spans

For any database call, regardless of database type:

```
db.system               "postgresql" | "mysql" | "redis" | "mongodb" | "elasticsearch" | ...
db.name                 "commerce"               # database name
db.operation.name       "SELECT" | "INSERT" | "FINDONE" | ...
db.collection.name      "orders"                 # table or collection name
server.address          "db.internal"
server.port             5432
db.query.text           "SELECT * FROM orders WHERE id = $1"  # sanitised, no param values
```

`db.query.text` should contain the query template with placeholders, never the actual parameter values. Including parameter values risks leaking PII and user data into your traces.

## Messaging Spans

For operations involving message brokers (Kafka, RabbitMQ, SQS, Pub/Sub):

```
messaging.system            "kafka" | "rabbitmq" | "aws_sqs" | "gcp_pubsub" | ...
messaging.destination.name  "orders.created"     # topic or queue name
messaging.operation.type    "publish" | "receive" | "process"
messaging.message.id        "msg-abc123"
messaging.batch.message_count  1
```

Producer spans have `messaging.operation.type = "publish"`. Consumer spans have `"receive"` (fetching from broker) and `"process"` (doing work on the message). These are separate spans linked by the message ID.

## Exception Events

When recording exceptions on a span, use the standard event name and attributes:

```
event name:              "exception"
exception.type           "java.io.IOException"
exception.message        "Connection refused"
exception.stacktrace     "java.io.IOException: Connection refused\n\tat ..."
exception.escaped        true   # true if the exception left the span's scope
```

All OTel SDKs populate these automatically when you call `span.recordException(e)`.

## RPC Spans

For gRPC and other RPC frameworks:

```
rpc.system              "grpc" | "connect_rpc" | "json_rpc"
rpc.service             "commerce.OrderService"
rpc.method              "CreateOrder"
rpc.grpc.status_code    0   # 0 = OK in gRPC status codes
```

## What Is Not a Semantic Convention

Semantic conventions cover infrastructure-level concepts: HTTP, databases, messaging, RPC, cloud providers, Kubernetes. They do not cover business logic.

Your own business attributes (`order.id`, `payment.provider`, `user.tier`) are custom attributes. Use a namespace prefix to distinguish them from OTel conventions and avoid future name collisions:

```
# OTel convention
http.response.status_code: 200

# Your custom attribute — namespaced to your domain
commerce.order.id: "ord-abc123"
commerce.payment.provider: "stripe"
```

Flat, unnamespaced names like `orderId` or `provider` will collide with future semantic conventions and with other teams' attributes.

## Attribute Naming Rules

When adding custom attributes, follow the same rules as the conventions:

- **Snake case with dots for namespacing:** `commerce.order.id`, not `commerceOrderId` or `Commerce_Order_ID`
- **Lowercase throughout:** `http.request.method`, not `HTTP.Request.Method`
- **Plural for arrays, singular for scalars:** `messaging.batch.message_count` (count), not `messages_count`
- **Consistent value types:** if an attribute is sometimes a string and sometimes an integer, pick one
- **Low cardinality for attributes that become metric labels:** `http.route` is low cardinality; `url.full` is high cardinality — never use `url.full` as a Prometheus label

## Instrumentation Libraries Handle Most of This

If you are using OTel auto-instrumentation libraries for your HTTP framework, database client, or messaging library, the library applies the correct semantic conventions automatically. You do not need to manually set `http.request.method` — the ASP.NET Core, Django, Express, or Spring Boot instrumentation does it.

Where you must apply conventions yourself is for custom spans covering your business logic. Use the conventions as a reference, pick the closest matching attributes, and apply the naming rules to your custom ones.

<!-- TODO: Add section on the GenAI semantic conventions (gen_ai.*) for LLM instrumentation -->
<!-- TODO: Add section on the K8s resource semantic conventions (k8s.* — link to resource attributes guide) -->
<!-- TODO: Add table of convention stability status for each domain (HTTP=stable, messaging=experimental, etc.) as of 2026 -->
<!-- TODO: Add section on the OpenTelemetry Schema URL and version pinning -->
