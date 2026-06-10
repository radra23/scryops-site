---
title: "How to Instrument a Java Spring Boot Service with OpenTelemetry"
date: 2026-06-10
draft: true
excerpt: "Instrument a Spring Boot service with OpenTelemetry — using the Java agent for zero-code auto-instrumentation or the manual SDK for fine-grained control, with traces, metrics, and logs all flowing to a Collector."
readtime: 8
tags: ["OpenTelemetry", "Tracing", "Observability", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Two approaches: Java agent (zero-code) vs manual SDK — when to use each
2. Java agent setup:
   - Download opentelemetry-javaagent.jar
   - JVM args: -javaagent, OTEL_* environment variables
   - What gets auto-instrumented: Spring MVC, JDBC, Kafka, gRPC, Redis
3. Manual SDK setup (for services that need custom spans):
   - Maven/Gradle dependencies: opentelemetry-sdk, opentelemetry-exporter-otlp
   - SDK configuration bean in Spring Boot
   - @WithSpan annotation for declarative instrumentation
   - Tracer.spanBuilder() for imperative instrumentation
4. Resource attributes configuration
5. Error handling: span.recordException(), StatusCode.ERROR
6. Micrometer bridge: exposing existing Micrometer metrics via OTel
7. Log correlation: MDC injection for trace context in Logback/Log4j2
8. Connecting to local Collector

Include: Maven pom.xml, application.properties, docker-compose.yml, example Controller
Source material note: language-specific guides are a standards domain
-->
