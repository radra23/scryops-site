---
title: "Your CI/CD Pipeline Is a Distributed System. Start Treating It Like One."
date: 2026-06-10
draft: true
excerpt: "Build times creep up, flaky tests accumulate, and deployment failures compound — all without anyone noticing until the release schedule slips. Instrumenting your CI/CD pipeline with the same rigour as your production services changes that."
readtime: 9
tags: ["CI/CD", "OpenTelemetry", "Observability", "Tracing"]
---

A CI/CD pipeline coordinates dozens of independent processes — source checkout, dependency resolution, compilation, test execution, container builds, deployment handoffs — across multiple machines and time spans. It fails in all the same ways distributed systems fail: dependency timeouts, flaky intermediate states, resource contention, partial progress with ambiguous outcome. But unlike production services, CI/CD pipelines are typically monitored with a green/red build badge and a log file you fetch manually after something breaks.

The result is predictable: build times creep up 30 seconds a week and nobody notices until they've doubled. A test suite drifts from 94% pass rate to 89%, buried in pipeline noise. A deployment step starts occasionally timing out, retrying silently, and adding five minutes to every release.

Treating your pipeline as a first-class observable system — with structured telemetry, continuous metrics, and alertable signals — changes that pattern.

## What to Instrument: Key Telemetry Points

Every pipeline stage is a source of signal. Three categories matter most.

**Build metrics** — the time and outcome of compilation and artifact creation:

- Build duration, absolute and as a trend over time
- Build status (success, failure, cancelled)
- Compiler warning count — useful for tracking technical debt accumulation
- Artifact size — catches accidental binary bloat before it reaches production

**Test metrics** — the health of the test suite as a whole and over time:

- Test execution time, total and per suite
- Test coverage percentage
- Pass/fail/skip counts per run
- Flaky test rate — tests that fail non-deterministically

**Deployment metrics** — the act of moving a build artifact to an environment:

- Deployment frequency (releases per day, week)
- Deployment duration (time from artifact ready to traffic serving)
- Deployment status (success, failure, rollback)
- Change volume per deployment (commits included, files changed)

{{< mermaid >}}
graph LR
    A[Code] --> B(Build)
    B --> C(Test)
    C --> D(Deploy)
    D --> E[Production]
    B --> F[Build Metrics]
    C --> G[Test Metrics]
    D --> H[Deployment Metrics]
{{< /mermaid >}}

These three categories map directly to the four DORA metrics — deployment frequency, lead time for changes, change failure rate, and time to restore service — which are derivable from pipeline telemetry once you instrument all three stages consistently.

## Automated Instrumentation Checks

Before build and deploy, run checks that verify the instrumentation itself — not just the application code. These gates prevent under-instrumented code from reaching production, where finding the gap costs significantly more.

Four categories of instrumentation checks:

**Presence checks** — verify that expected telemetry is being emitted. A service that was instrumented three months ago should still be emitting traces on the main request path. A presence check fails the build if it is not.

**Correctness checks** — validate the structure and semantics of emitted telemetry. Required span attributes are present. Log fields conform to the defined schema. Metric names follow the naming convention. Histogram bucket boundaries are appropriate for the operation being measured.

**Coverage checks** — confirm that instrumentation covers critical paths and components, not just the happy path. A service can pass presence checks while having zero instrumentation on its error-handling code paths.

**Compliance checks** — enforce that instrumentation adheres to the organisation's standards: no PII in span attributes, no high-cardinality unbounded labels on metrics, no secrets in log output.

{{< mermaid >}}
graph TD
    A[Source Code] --> B{Instrumentation Checks}
    B -->|Pass| C[Build and Deploy]
    B -->|Fail| D[Fix Instrumentation]
    D --> A
    C --> E[Production]
{{< /mermaid >}}

These checks are most effective as pre-merge gates rather than post-deployment audits. Catching a missing trace attribute in a pull request costs minutes. Finding that attribute's absence after a production incident costs hours.

## Observability as Code

Instrumentation configuration — sampling rules, attribute allowlists, Collector pipelines, alert thresholds — tends to live in ad-hoc scripts and team wikis. The result is configuration drift: the production Collector config no longer matches what was tested, alert thresholds are changed without review, and nobody can explain when a sampling policy was last updated.

Observability as Code applies the same version control, review, and deployment practices to telemetry configuration that your team already uses for application code:

- Collector configurations in version control, deployed through the same CD pipeline as the services they monitor
- Alert rules defined as code (Grafana JSON, Prometheus alerting rules YAML) reviewed as pull requests
- Sampling policies expressed as code artifacts subject to the same change management as application deployments
- Instrumentation standards tested in CI alongside application unit tests — the check that ensures a span has the required attributes is a test, not a convention in a wiki

{{< mermaid >}}
graph LR
    A[Instrumentation Code] --> B[Application Code]
    B --> C[CI/CD Pipeline]
    C --> D[Test Environment]
    C --> E[Production Environment]
    D --> F[Telemetry Backend]
    E --> F
{{< /mermaid >}}

The practical effect is that your telemetry configuration becomes auditable. "When did we change the sampling rate for checkout traces?" has an answer in git history rather than team memory.

## Performance Regression Detection

Performance regressions introduced in individual commits are hard to catch in production — by the time a trend is visible in dashboards, multiple changes have landed and attribution is difficult. Detecting regressions in CI, before a change ships, makes attribution straightforward.

Four practical techniques:

**Baseline comparison** — capture performance metrics from the current run and compare against a historical baseline. A build that shows more than 10% regression against the rolling average of the last 30 runs fails. The threshold is configurable per service and per operation.

**Canary testing** — route a small percentage of traffic to the new version in a pre-production environment, compare its performance against the stable version, and fail the deploy if the canary shows degradation outside the defined error budget.

**Load testing** — run a load test against the build under controlled conditions. Failures and latency violations at a specified load level become hard pipeline gates.

**Anomaly detection** — apply statistical analysis to performance metrics from each build to identify patterns that deviate from the normal range — not just absolute threshold violations. A build that is 8% slower than usual across every operation may not breach any single threshold but does breach a statistical pattern.

{{< mermaid >}}
graph TD
    A[New Code] --> B[CI/CD Pipeline]
    B --> C{Performance Regression Detection}
    C -->|No Regression| D[Deploy to Production]
    C -->|Regression Detected| E[Fail Pipeline]
    E --> F[Alert Team]
    F --> G[Fix Performance Issue]
    G --> A
{{< /mermaid >}}

When regression detection runs in the pipeline, the feedback loop closes at commit time: commit → build → performance test → fail with attribution → fix. The regression never reaches production users.

<!-- TODO: OpenTelemetry semantic conventions for CI/CD — cicd.pipeline.name, cicd.pipeline.run.id, cicd.task.name attributes; VCS conventions for commit SHA and branch; these are still stabilising as of 2026 -->
<!-- TODO: Tool-specific instrumentation — GitHub Actions with otel-export-trace action; GitLab CI native OTel support (available since 15.x); Jenkins OpenTelemetry plugin (v2+) -->
<!-- TODO: Build steps as spans — modelling the pipeline run as a trace: pipeline run as root span, each stage as a child span, each step as a grandchild; instrumenting test suite runs as span events with pass/fail counts as span attributes -->
<!-- TODO: Connecting CI traces to production — linking the deploy span that built version X to production spans running version X; carrying build metadata (commit SHA, pipeline run ID) into production resource attributes via deployment tooling, not the application; service.version in production should be set by the deploy step, not hardcoded -->
<!-- TODO: Build success rate SLOs — treating CI reliability as a service level; alerting when the 7-day rolling build success rate drops below 95%; error budgets for pipeline reliability -->
<!-- TODO: Grafana dashboard for pipeline health — build time trend, flaky test rate, deployment frequency, DORA metrics derived from pipeline telemetry -->
