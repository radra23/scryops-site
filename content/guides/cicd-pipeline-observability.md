---
title: "Your CI/CD Pipeline Is a Distributed System. Start Treating It Like One."
date: 2026-06-10
draft: true
excerpt: "Build times creep up, flaky tests accumulate, and deployment failures compound — all without anyone noticing until the release schedule slips. Instrumenting your CI/CD pipeline with the same rigour as your production services changes that."
readtime: 9
tags: ["CI/CD", "OpenTelemetry", "Observability", "Tracing"]
---

<!-- TODO: Draft this guide -->
<!--
Source material: the standards README identifies "deployment context specifications" as part of
service identification standards. The deployment context (environment, version, cluster) that
gets stamped on production telemetry originates in the CI/CD pipeline. This guide should
connect the deployment event to the resource attributes that appear in production spans.

Specifically:
- The `service.version` in a production span should match the version built and deployed by CI
- The `deployment.environment` should be set by the deploy step, not the application
- CI/CD traces and production traces should be linkable: the deploy span that promoted
  version X should be discoverable from a production span running version X

Sections to cover:
1. Why CI/CD pipelines need observability (not just logs)
2. OpenTelemetry for CI/CD: the emerging semantic conventions
3. GitHub Actions instrumentation with otel-export-trace action
4. GitLab CI instrumentation
5. Jenkins OpenTelemetry plugin
6. What to instrument: build steps as spans, test suites as spans, deploy events
7. Useful metrics: build duration trends, flaky test rate, deployment frequency
8. Connecting CI spans to production deployment traces
9. Alerting on CI/CD health: build success rate SLOs
10. Visualising pipeline health in Grafana
-->
