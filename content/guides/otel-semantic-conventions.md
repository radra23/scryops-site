---
title: "OTel Semantic Conventions: The Standard Dictionary for Telemetry Attributes"
date: 2026-11-16
draft: false
excerpt: "When every team invents its own attribute names, nobody can query across services. OpenTelemetry semantic conventions are the shared vocabulary that fixes it. Here's what they cover as of v1.45.0, which names changed, and how to name your own attributes."
readtime: 8
tags: ["OpenTelemetry", "Observability", "Best Practices", "Tracing"]
card:
  title: "The Standard Dictionary for Telemetry Attributes"
---

Try correlating HTTP errors across fifty services when one team writes `http.status`, another writes `status_code`, a third writes `response.status_code`, and a fourth buries the status in a log message with no structured field at all. That isn't a thought experiment. It's what you get by default when nobody agrees on names.

OpenTelemetry semantic conventions are the agreement. They're a published dictionary of attribute names, their types, and their allowed values. When every service uses the same name for the same thing, one query covers the whole organisation.

Everything below is checked against semantic conventions **v1.45.0**, released on 2 November 2026. The conventions move, so the first thing to learn is how to tell which parts hold still.

## Stability levels

Every convention carries a stability level. There are five, plus a marker for names on their way out:

- **Stable**: safe to build on. A stable name doesn't change without a long migration period.
- **Release candidate**: close to stable, and unlikely to change.
- **Development**, **alpha**, **beta**: still being worked out. Names can be renamed or dropped between releases. Anything with no level stated counts as development.
- **Deprecated**: replaced or retired. The registry says what to use instead.

Older posts call the unfinished level "experimental". The current docs call it development.

Stability is set per attribute, not only per domain, so a stable page can still hold a development attribute. Here's where the domains in this guide stand:

| Domain | Status in v1.45.0 |
|---|---|
| HTTP spans | Stable |
| Database spans | Stable |
| RPC and gRPC spans | Stable |
| Exceptions in logs | Stable |
| Exceptions on spans | Deprecated, replaced by exceptions in logs |
| Messaging spans | Development |
| Generative AI | Development, and moved to its own repository |

The [semantic conventions documentation](https://opentelemetry.io/docs/specs/semconv/) is the source of truth. The [attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/) lists every name with its level.

## HTTP spans

These are the conventions you'll meet first. For an inbound request handled by a server:

```
http.request.method        "GET" | "POST" | "PUT" | "DELETE" | ...
url.path                   "/v1/orders/42"
url.query                  "expand=items"
url.scheme                 "https"
http.route                 "/v1/orders/{id}"     # the template, not the specific path
http.response.status_code  200
server.address             "api.example.com"
server.port                443
network.protocol.version   "1.1" | "2"
user_agent.original        "Mozilla/5.0 ..."
```

For an outbound request made by a client:

```
http.request.method        "GET"
url.full                   "https://api.stripe.com/v1/charges"
server.address             "api.stripe.com"
server.port                443
http.response.status_code  200
```

Notice the split. A server span records the URL in parts (`url.path`, `url.query`, `url.scheme`). A client span records `url.full`.

**Span status depends on which side you're on.** For 5xx responses, set the span status to `Error` on both sides. For 4xx responses, a server span leaves the status unset, because the server did its job and the caller sent a bad request. A client span sets `Error`, because from the caller's side the request failed. This is the rule most hand-written instrumentation gets wrong.

## Database spans

The database conventions are stable, and two names changed on the way there. If your dashboards still filter on `db.system` or `db.name`, they're reading deprecated attributes.

```
db.system.name        "postgresql" | "mysql" | "redis" | "mongodb" | "elasticsearch" | ...
db.namespace          "commerce"               # the database name
db.operation.name     "SELECT" | "INSERT" | "findAndModify" | ...
db.collection.name    "orders"                 # table or collection
db.query.text         "SELECT * FROM orders WHERE id = $1"
db.query.summary      "SELECT orders"          # low-cardinality summary of the query
server.address        "db.internal"
server.port           5432
```

Keep `db.query.text` to the query with its placeholders, never the parameter values. Values are where customer emails and card numbers ride into your trace backend. [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) covers what happens next.

## Messaging spans

For brokers such as Kafka, RabbitMQ, SQS, and Pub/Sub. These conventions are still in development, so expect more renames. One has already happened: `messaging.system` is now `messaging.system.name`.

```
messaging.system.name          "kafka" | "rabbitmq" | "aws.sqs" | "gcp.pubsub" | ...
messaging.destination.name     "orders.created"    # topic or queue
messaging.operation.type       "create" | "send" | "receive" | "process" | "settle"
messaging.operation.name       "send"              # the name the client library uses
messaging.message.id           "msg-abc123"
messaging.batch.message_count  1
```

A producer span has the type `send`. The old `publish` value is deprecated. A consumer has two kinds of span: `receive` for fetching from the broker, and `process` for doing the work.

Producer and consumer spans aren't tied together by the message ID. The producer injects its trace context into the message headers, and the consumer span carries a **span link** back to that context. [Context propagation](/guides/otel-context-propagation/) explains how the context gets into the headers.

## Exceptions

This is the biggest change if you learned OTel a while ago. Recording an exception as a span event is now deprecated. The current convention records exceptions as **logs**, which carry the trace and span IDs so they still show up beside the span.

The attributes didn't change:

```
exception.type        "java.io.IOException"
exception.message     "Connection refused"
exception.stacktrace  "java.io.IOException: Connection refused\n\tat ..."
```

`exception.escaped` is gone from that list. It's deprecated, and the guidance now is to not record exceptions that get handled inside the span at all.

You don't have to change anything today. Instrumentation keeps emitting span events by default, and the migration is opt-in through one environment variable:

```bash
# logs/dup emits both the span event and the log while you move dashboards over.
# logs emits the log only.
export OTEL_SEMCONV_EXCEPTION_SIGNAL_OPT_IN=logs/dup
```

Support for that variable depends on your SDK and instrumentation versions, so check their release notes before you rely on it.

## RPC spans

The RPC conventions are stable now, and almost every name in older gRPC examples has changed:

| Old name | Current name |
|---|---|
| `rpc.system` | `rpc.system.name` |
| `rpc.service` + `rpc.method` | `rpc.method`, fully qualified |
| `rpc.grpc.status_code` (integer) | `rpc.status_code` (string) |

```
rpc.system.name    "grpc" | "connectrpc" | "jsonrpc" | "dubbo"
rpc.method         "commerce.OrderService/CreateOrder"
rpc.status_code    "OK" | "DEADLINE_EXCEEDED" | ...
server.address     "orders.internal"
```

For gRPC, every status code except `OK` counts as an error. An alert that still checks `rpc.grpc.status_code != 0` will stop matching once your instrumentation upgrades, and it'll stop quietly.

## Renames you'll hit

The pattern above repeats across the registry. These are the ones that break existing queries most often:

| Deprecated | Use instead |
|---|---|
| `db.system` | `db.system.name` |
| `db.name` | `db.namespace` |
| `messaging.system` | `messaging.system.name` |
| `rpc.system` | `rpc.system.name` |
| `rpc.grpc.status_code` | `rpc.status_code` |
| `deployment.environment` | `deployment.environment.name` |

Instrumentation libraries don't flip to new names overnight. For most stabilised domains they keep emitting the old names until you opt in with `OTEL_SEMCONV_STABILITY_OPT_IN`. The accepted values differ per domain and per library, so read the migration guide for the one you're upgrading.

Every release also has a **schema URL**, such as `https://opentelemetry.io/schemas/1.45.0`. Instrumentation stamps it on the telemetry it produces, so you can tell which version of the dictionary a span was written in.

## What isn't a semantic convention

The conventions cover what's common across systems: HTTP, databases, messaging, RPC, cloud providers, Kubernetes. They don't cover your business.

Attributes like an order ID or a payment provider are yours to name. Give them a prefix so they can't collide with a future convention:

```
# OTel convention
http.response.status_code: 200

# Your attributes, prefixed with your application or domain
commerce.order.id: "ord-abc123"
commerce.payment.provider: "stripe"
```

The spec's advice is to prefix with your application name when the attribute stays inside your company, and with your company's reverse domain name (`com.example.order.id`) when it might travel outside. Never reuse an existing OTel namespace such as `http.` or `db.` for your own attributes. Flat names like `orderId` or `provider` are the ones that collide.

## Naming rules for your own attributes

Follow the same rules the conventions follow:

- **Dots for namespaces, snake_case inside a name.** `commerce.order.id` and `commerce.retry_count`, not `commerceOrderId` or `Commerce_Order_ID`.
- **Lowercase throughout.** `http.request.method`, not `HTTP.Request.Method`.
- **Plural only for arrays.** `process.command_args` is a list, so it's plural. A single value gets a singular name.
- **One type per attribute.** If it's sometimes a string and sometimes an integer, pick one.
- **Low cardinality for anything that becomes a metric label.** `http.route` is bounded. `url.full` isn't, and it should never become a Prometheus label.

## Instrumentation libraries do most of this for you

If you use OTel instrumentation for your HTTP framework, database client, or messaging library, it applies the conventions itself. You don't set `http.request.method` by hand. The ASP.NET Core, Django, Express, or Spring Boot instrumentation does it.

Your job starts with custom spans around your own business logic. Look up the closest convention, use its attributes where they fit, and name the rest by the rules above.

Next, give all of that telemetry an identity: [OTel Resource Attributes](/guides/otel-resource-attributes-and-service-naming/) covers the attributes that say which service, version, and environment produced it.

<!-- TODO: Add section on the GenAI semantic conventions (gen_ai.*), now in open-telemetry/semantic-conventions-genai; the LLM observability guide covers them -->
<!-- TODO: Add section on the K8s resource semantic conventions (k8s.*) -->
