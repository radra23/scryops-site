---
title: "How to Instrument a Java Spring Boot Service with OpenTelemetry"
date: 2026-10-01
draft: false
excerpt: "Instrument a Spring Boot service with the OpenTelemetry Java agent or the Spring Boot starter: traces, metrics and logs with no code, then your own spans and metrics, the Micrometer bridge and log correlation. All verified against a local Collector."
readtime: 7
tags: ["OpenTelemetry", "Tracing", "Observability", "How-to"]
---

Java has the most mature zero-code OpenTelemetry story of any runtime. Attach one agent jar to the JVM and a Spring Boot service exports traces, metrics and logs with no code changes at all. This guide sets that up, covers the Spring Boot starter for when an agent isn't an option, adds your own spans and metrics, and checks what arrives.

Everything below was run against a Spring Boot 4.1 service on Java 21, with the OpenTelemetry Java agent and Spring Boot starter 2.31.1 and Collector 0.161.0.

## Agent or Starter?

| | Java agent | Spring Boot starter |
|---|---|---|
| How | A JVM startup flag | A Maven/Gradle dependency |
| Code changes | None | None for the basics |
| Coverage | Broad: servlet containers, HTTP clients, JDBC, Kafka, gRPC, Redis, logging frameworks, and more | Spring's own components (Web MVC, WebFlux, RestClient, Kafka, JDBC) and logging |
| Use when | You can control the JVM's startup flags: the default | Native images, or environments that don't allow agents |

Start with the agent. Its coverage is wider, and upgrading it doesn't mean rebuilding the application. A third option, wiring the SDK up yourself, is only worth it for libraries and unusual setups. Even then, the SDK's autoconfigure module reads the same environment variables as the agent.

## The Java Agent

Download a pinned version of the agent and add it to the JVM's startup:

```dockerfile
FROM eclipse-temurin:21-jre
ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.31.1/opentelemetry-javaagent.jar /otel/opentelemetry-javaagent.jar
COPY target/checkout.jar /app/checkout.jar
ENTRYPOINT ["java", "-javaagent:/otel/opentelemetry-javaagent.jar", "-jar", "/app/checkout.jar"]
```

Configure it with the standard environment variables:

```bash
OTEL_SERVICE_NAME=checkout-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=1.4.2,deployment.environment.name=production
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318   # the agent defaults to http/protobuf
```

Note the port: the Java agent exports over HTTP/protobuf by default, so it talks to the Collector's **4318**, not the gRPC port 4317 that most other SDKs use. Set `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` if you'd rather use 4317.

With no code changes, the test service exported:

- a `SERVER` span per request, named after its route (`POST /checkout/{orderId}`), and a `CLIENT` span for each outgoing call made through Spring's `RestClient`;
- `http.server.request.duration` and `http.client.request.duration` histograms, plus JVM memory, GC and thread metrics;
- every Logback log record, over OTLP, with the trace and span IDs of the request that wrote it. Errors also carried `exception.type`, `exception.message` and `exception.stacktrace`.

The agent also puts `trace_id`, `span_id` and `trace_flags` into the SLF4J MDC, so your *console* log pattern can show them too; [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) has the Logback pattern. If your logs are already collected some other way and you don't want a second copy over OTLP, set `OTEL_LOGS_EXPORTER=none`.

## The Spring Boot Starter

If the agent isn't an option, add the starter through the instrumentation BOM:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>io.opentelemetry.instrumentation</groupId>
      <artifactId>opentelemetry-instrumentation-bom</artifactId>
      <version>2.31.1</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>io.opentelemetry.instrumentation</groupId>
    <artifactId>opentelemetry-spring-boot-starter</artifactId>
  </dependency>
  <!-- Required for @WithSpan — see below. Spring Boot 3: spring-boot-starter-aop -->
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aspectj</artifactId>
  </dependency>
</dependencies>
```

It reads the same `OTEL_*` environment variables (and `otel.*` properties in `application.properties`). The test service produced the same spans, metrics and correlated logs as with the agent, from Spring's own instrumentation instead of the servlet container's.

**The trap is the second dependency.** The starter implements `@WithSpan` with Spring AOP. Without an AOP starter on the classpath, `@WithSpan` is silently ignored: in testing, no span was created, and the attributes the method set landed on the HTTP request's span instead. On Spring Boot 4 that starter is `spring-boot-starter-aspectj`; on Spring Boot 3 it's `spring-boot-starter-aop`. It also means the usual Spring AOP rule applies: a `@WithSpan` method called from another method *in the same class* doesn't go through the proxy, and gets no span. The agent rewrites the bytecode instead, so neither limitation applies there.

## Your Own Spans

Framework instrumentation covers the boundaries. For business operations, annotate the method:

```java
// io.opentelemetry.instrumentation:opentelemetry-instrumentation-annotations (version from the BOM)
@Service
class PaymentService {
  private static final Logger log = LoggerFactory.getLogger(PaymentService.class);

  @WithSpan("payment.charge")
  PaymentResult charge(@SpanAttribute("order.id") String orderId, BigDecimal amount) {
    Span span = Span.current();                 // the span @WithSpan just started
    span.setAttribute("payment.amount", amount.doubleValue());
    try {
      PaymentResult result = gateway.charge(orderId, amount);
      if (result.declined()) {
        // A declined card is a business outcome, not a system error: no ERROR status
        span.setAttribute("payment.decline_code", result.declineCode());
      }
      return result;
    } catch (RuntimeException e) {
      span.recordException(e);                  // an "exception" event on the span
      span.setStatus(StatusCode.ERROR, e.getMessage());
      log.error("Payment failed for order {}", orderId, e);
      throw e;
    }
  }
}
```

In the test, this produced a `payment.charge` span as a child of the request span, with `order.id` and `payment.amount`. On the failing call it had status `ERROR` and an `exception` event.

Where an annotation doesn't fit, such as a span around part of a method or inside a loop, build the span yourself:

```java
Tracer tracer = GlobalOpenTelemetry.getTracer("commerce.payments");

Span span = tracer.spanBuilder("payment.fraud_check").startSpan();
try (Scope scope = span.makeCurrent()) {   // makes it the parent of anything started inside
  fraudCheck.run(order);
} finally {
  span.end();                               // always end it, or it is never exported
}
```

With the starter, inject the `OpenTelemetry` bean instead of calling `GlobalOpenTelemetry`.

## Your Own Metrics

There are two routes, depending on whether the service already uses Micrometer.

**The OpenTelemetry metrics API** works the same way with the agent and the starter:

```java
private static final LongCounter CHARGES = GlobalOpenTelemetry.getMeter("commerce.payments")
    .counterBuilder("payment.charges")
    .setUnit("{charge}")
    .setDescription("Payment charge attempts")
    .build();

private static final AttributeKey<String> OUTCOME = AttributeKey.stringKey("payment.outcome");

CHARGES.add(1, Attributes.of(OUTCOME, "charged"));
```

**Existing Micrometer metrics** need the agent's Micrometer bridge, which is **off by default**. In testing, a Micrometer `Counter` registered in the app never reached the Collector until the bridge was turned on:

```bash
OTEL_INSTRUMENTATION_MICROMETER_ENABLED=true
```

Turning it on has a cost: the bridge exports *everything* in the Micrometer registry, including Spring Boot Actuator's own JVM metrics. The test service went from 20 metric streams to 80. `jvm.memory.used` arrived twice, once from the agent (unit `By`) and once from Micrometer (unit `bytes`), and any dashboard summing it double-counts. If you enable the bridge, disable one of the two JVM sources, or drop the duplicates in the Collector.

Either way, keep attribute values to a small, known set. An outcome with three values is fine; an order ID as an attribute creates a new time series per order.

## Verify Against a Local Collector

Run a Collector that prints what it receives, with both OTLP ports open, since the agent uses 4318:

```yaml
# docker-compose.yml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.161.0   # pin it; :latest changes under you
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP — the Java agent's default
    volumes:
      - ./collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro
```

```yaml
# collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:  { receivers: [otlp], exporters: [debug] }
    metrics: { receivers: [otlp], exporters: [debug] }
    logs:    { receivers: [otlp], exporters: [debug] }
```

Then send a few requests, including one that fails, and check the Collector's output for:

- **Resource:** `service.name`, `service.version` and `deployment.environment.name` on spans, metrics and logs
- **Spans:** a `SERVER` span per request with an `http.route`, `CLIENT` spans and your `payment.charge` span as its children, and `ERROR` status only where something actually failed
- **Metrics:** `http.server.request.duration` and your own metrics, after the first export interval (60 seconds by default; set `OTEL_METRIC_EXPORT_INTERVAL=5000` locally)
- **Logs:** the same trace ID as the request's spans

From here:

- [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/): the MDC keys in your console output, and the manual route without the agent
- [Context Propagation](/guides/otel-context-propagation/): keeping traces connected through executors, queues and services. The agent carries context into executors by itself; without it, wrap them with `Context.taskWrapping`
- [How to Configure OTel Collector Tail Sampling](/howtos/configure-collector-tail-sampling/): once all of this is flowing, deciding what to keep
