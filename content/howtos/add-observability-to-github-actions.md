---
title: "How to Add OpenTelemetry Tracing to GitHub Actions"
date: 2026-06-10
draft: true
excerpt: "Instrument your GitHub Actions workflows so build steps appear as spans, test failures are captured as span events, and you can trace a deployment from code commit to production release."
readtime: 6
tags: ["CI/CD", "OpenTelemetry", "Tracing", "How-to"]
---

<!-- TODO: Draft this how-to -->
<!--
Steps to cover:
1. Add the otel-export-trace GitHub Action to your workflow
2. Configure OTLP endpoint and auth token as repository secrets
3. Map workflow steps to OTel span attributes
4. Capture test results as span events (JUnit XML → OTel)
5. Propagate trace context to deployment steps (linking CI trace to deployment trace)
6. Visualise workflow traces in Grafana Tempo
7. Build a build duration SLO with Prometheus recording rules
8. Alert on build success rate dropping below threshold

Include: annotated workflow YAML, Grafana dashboard screenshot description
-->
