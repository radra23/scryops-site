---
title: "Observability as Code: Managing Telemetry Artifacts Like Production Software"
date: 2026-06-12
draft: true
excerpt: "Dashboards hand-clicked into existence at 2am have no reviewers, no tests, and no rollback path. Observability as Code applies the same Git-PR-CI discipline to alerts, dashboards, SLOs, collector pipelines, and synthetic checks that application code has had for years."
readtime: 9
tags: ["Observability", "OpenTelemetry", "SLOs", "Best Practices", "Grafana"]
---

Observability as Code (OaC) is the practice of managing every observability configuration — dashboards, alerts, SLOs, collector pipelines, instrumentation, and synthetic monitors — as version-controlled, declaratively-defined artifacts that flow through the same Git/CI/CD machinery as application code.

The operational driver is scale: modern stacks have hundreds of microservices, multiple environments, and ephemeral infrastructure where manual configuration cannot keep up. Grafana Labs' 2026 Observability Survey (1,363 respondents, 76 countries, published March 2026) found complexity/overhead, signal-to-noise, and cost as the top three concerns — exactly the problems that codified, modular, reusable observability artifacts target. The same survey found the average organization uses eight distinct observability technologies, down from nine the prior year, suggesting consolidation pressure. As with all vendor-run surveys, the self-selected Prometheus/OTel-leaning respondent base means treat trend direction as more reliable than absolute numbers.

The contrast with UI-driven observability is significant enough to lay out explicitly:

| Dimension | UI-driven | Observability as Code |
|---|---|---|
| Source of truth | Vendor UI / database | Git repo |
| Change management | Click in production console | Pull request + code review |
| Auditability | "Who changed that 3am alert?" | `git blame` |
| Multi-env consistency | Manual replication, drift | Templated promotion dev → staging → prod |
| Rollback | Manually re-create | `git revert` |
| Testing | None | `promtool test rules`, schema validation, CI lint |
| Authoring | Ops/SRE-only | Developers ship monitors alongside code |
| Disaster recovery | Re-create from memory | `terraform apply` / `kubectl apply` |

## Standards Landscape

OaC depends on standards that are stable enough to build toolchains against. The ecosystem has converged on a small set.

**OpenTelemetry Declarative Configuration.** As of March 2026, the OTel project stabilized the JSON schema for the data model, the YAML file representation, the in-memory data model, and the `OTEL_CONFIG_FILE` environment variable. A single YAML file per service can now pin tracing, metrics, and logging pipelines — replacing environment-variable soup. The Go reference implementation ships in `go.opentelemetry.io/contrib/otelconf`; the Java agent (v2.21+) and JavaScript SDK also consume the file. .NET and Python support are in progress. Verify SDK support for your language stack before committing to the file-based approach. The OTel Collector has long used YAML pipeline configs (`receivers`/`processors`/`exporters`/`extensions`/`service.pipelines`) — declarative configuration extends those patterns uniformly into SDKs.

**OpenSLO.** Released as v1.0 in May 2022 by Nobl9 with contributions from GitLab, Lightstep, Red Hat, and Sumo Logic. A YAML, Kubernetes-style declarative spec for `SLI`, `SLO`, and `AlertPolicy` objects. Sloth, Pyrra, and Nobl9 all interoperate with OpenSLO v1. A v2alpha is in development as of 2026 but has not reached a finalized v2.0 — build against v1 if you need stability.

**Prometheus Operator CRDs.** The de facto Kubernetes-native standard for alerts and scrape configuration as code: `PrometheusRule`, `ServiceMonitor`, `PodMonitor`, `Probe`, `ScrapeConfig`, `AlertmanagerConfig`. The `monitoring.coreos.com/v1` CRDs are stable and reconciled by Prometheus Operator from Git via Flux or Argo CD.

**Perses.** A CNCF Sandbox project aiming to be the vendor-neutral *Open Dashboard Model*: Go and CUE SDKs, strict typing, a Kubernetes operator with CRDs, and a `percli` CLI. Adopted by Red Hat (OpenShift traces UI), Chronosphere, and SAP. It is the first serious attempt at a portable dashboard specification that is not Grafana-specific.

## Tool Ecosystem

**Instrumentation and collector pipelines:**

- **OpenTelemetry SDKs** — declarative YAML config (stable 2026); Java most complete, .NET/Python in progress
- **OTel Collector** + **Collector Builder (`ocb`)** — receivers/processors/exporters in YAML; OTTL (OpenTelemetry Transformation Language) for in-pipeline data manipulation
- **OTel eBPF Instrumentation (OBI)** — zero-code instrumentation declared per-service in YAML; targeting stable 1.0 in 2026

**Dashboards as code:**

- **Grafana Foundation SDK** (Go, TypeScript, Python, Java, PHP) — official replacement for Grafonnet (deprecated as of Grafana 12/13); strongly-typed builders emitting Grafana's v2 JSON schema; deploy via `gcx` CLI or the versioned `/apis/` endpoints
- **Grafana Git Sync** — bidirectional sync between a Grafana instance and a GitHub/GitLab/Bitbucket repo, including screenshot diffs in PR comments; GA in Grafana 13 (April 2026); dashboards and folders only — alerts on roadmap
- **Grafana Operator** — `GrafanaDashboard`/`GrafanaAlertRule`/`GrafanaDataSource` CRDs reconciled from Git
- **Perses** (Go SDK, CUE SDK, `percli dac build` + `percli apply`) — vendor-neutral alternative
- **Terraform `grafana` provider** / **Crossplane Grafana provider** — for teams preferring IaC-native workflow
- Grafonnet, grafanalib, Grabana are legacy; treat as read-only for inherited stacks

**Alerts and SLOs as code:**

- **Prometheus alerting rules** in Git (`groups: rules: - alert:`) shipped via `PrometheusRule` CRDs
- **`promtool test rules`** — unit tests for alerting/recording rule expressions; run in CI on every PR
- **Sloth** (CLI + Kubernetes operator) — generates multi-window multi-burn-rate alerts and recording rules from a `PrometheusServiceLevel` resource; v0.14.0 (October 2025) added contrib SLO plugins and VictoriaMetrics support; ~2.3k GitHub stars
- **Pyrra** (CLI + Kubernetes operator + UI) — similar to Sloth with an added SLO browse UI; monthly-cadence releases; ~1.5k stars; maintained by its authors in their free time
- **Nobl9** — SaaS full OpenSLO v1 implementation
- **Terraform/Pulumi** `datadog`, `newrelic`, `grafana` providers for SaaS-native alert rules

**Synthetic monitoring as code:**

- **Checkly CLI** — reuses existing Playwright `*.spec.ts` files as scheduled global monitors; `npx checkly test` in CI, `npx checkly deploy` to production; checks live in the app repository alongside the code they test
- **Datadog Synthetics** via `datadog_synthetics_test` Terraform resource
- **Grafana Synthetic Monitoring** via Terraform
- **New Relic Synthetics** via Pulumi/Terraform

**GitOps deployment:**

- **Flux CD / Argo CD** — reconcile `PrometheusRule`, `GrafanaDashboard`, `ServiceLevelObjective` (Sloth/Pyrra), and Perses CRDs from Git to clusters
- **Terraform** — `grafana`, `datadog`, `newrelic` providers for SaaS backends; use `for_each` over YAML-loaded maps to generate dozens of monitors from a single module
- **Pulumi** — same backends with strongly-typed Python/TypeScript/Go/.NET

## Best Practices

**1. Version everything in Git, organized by environment.** A conventional layout:

```
observability/
  dashboards/         # Perses or Grafana Foundation SDK source
  alerts/             # PrometheusRule YAMLs or Terraform .tf
  slos/               # OpenSLO YAMLs or Sloth / Pyrra specs
  collector/          # OTel Collector configs per environment
  terraform/          # Datadog, New Relic, Grafana Cloud
  synthetics/         # Checkly *.check.ts and Playwright *.spec.ts
  .github/workflows/  # Validation + apply pipelines
```

**2. Treat observability changes like code changes.** PR review by SRE and service owner, mandatory CI checks (linting, `promtool test rules`, schema validation), and protected branches. Grafana Git Sync generates screenshot diffs in PR comments for dashboard changes — reducing friction without sacrificing audit.

**3. Test rules; don't just lint them.** Write executable unit tests for alerting rules with `promtool test rules`: inject synthetic `input_series`, assert which alerts fire at specific `eval_time`s, with which labels and annotations. An alerting rule without a test is a rule you haven't confirmed fires correctly. Run on every PR.

**4. Modularize ruthlessly.** A reusable Terraform or Helm module per service archetype (HTTP API, async worker, batch job) that emits a standard bundle of monitors, dashboards, and SLOs from a small set of inputs (`service_name`, `team`, `environment`, `alert_channel`, error/latency thresholds). Every new service gets the bundle for free. The Perses Community Dashboards repository demonstrates this pattern — a Go module of composable panels that downstream teams import and extend.

**5. Promote artifacts across environments.** Dev → staging → prod should be identical except for selector labels and thresholds. This eliminates the "alert fires in prod but not staging" failure class.

**6. Require `runbook_url` and `dashboard_url` on every alert.** Alerts without a linked runbook should fail CI lint. An alert that fires at 3am with no linked runbook is noise, not signal — it tells the responder they're on their own.

**7. Bake observability into service scaffolding.** Use Backstage Scaffolder templates or equivalent so every new service ships with its dashboards, SLOs, and alerts on day one. No service should reach production blind.

**8. Centralize Collector configs but allow per-service overrides.** Use `OTEL_CONFIG_FILE` with environment variable substitution; apply the OTel eBPF Instrumentation (OBI) for languages and runtimes without good auto-instrumentation.

**9. Manage secrets correctly.** Never commit API keys or tokens. Use Vault/Secrets Manager with env-var expansion in Collector and Terraform configs; all major Terraform providers support `sensitive = true` variables.

**10. Enforce an alert taxonomy in CI.** Define severity, owner team, runbook, dashboard, and on-call routing fields upfront; enforce their presence via OPA/conftest policies running in every PR pipeline.

## Challenges and Anti-Patterns

**Wrapping UI clicks in Terraform without modules.** Moving sprawl from the UI to Git does not make it manageable — it just makes it text. TechTarget's critique: "The repeatable best practices and ideal collaboration aspects of observability as code are more of a 'nice to have,' and many vendors are vague on the details." Modularize from day one; raw resource-per-service configurations don't scale.

**State management contention.** Terraform state for observability grows large and contended when monolithic. Partition state per domain or team. Kubernetes Operators (Prometheus Operator, Grafana Operator, Perses Operator) avoid this problem entirely by storing desired state in etcd.

**UI-Git drift.** Common with Datadog and New Relic where UI edits don't automatically surface as PRs. Mitigations: mark managed resources as read-only in the UI, run nightly `terraform plan` drift-detection jobs, or use Git Sync-style bidirectional workflows where available.

**Jsonnet learning curve.** Monitoring Mixins (the Prometheus community's Jsonnet-based convention for bundling dashboards + alert rules + recording rules) are powerful but Jsonnet is unfamiliar to most engineers. Teams routinely fetch the rendered YAML output and bypass the Jsonnet source, which defeats composability and updates. The Grafana Foundation SDK (Go/TypeScript/Python/Java/PHP) and Perses Go SDK address this by using languages teams already know.

**Big-bang migrations.** Migrating hundreds of existing UI dashboards in one cut overwhelms reviewers and creates merge conflicts. Start with the 10–20% of dashboards and alerts covering the most critical services; expand incrementally.

**Untested rules.** Alerting rules without `promtool test rules` coverage routinely ship with broken PromQL or miscalibrated thresholds — the rule passes linting but never actually fires, or fires on every alert evaluation. Unit tests are table-stakes, not optional.

**Over-collection without a budget.** Brute-force telemetry collection from a declarative Collector config is easy to write and expensive to run. Apply `filter`, `tail_sampling`, and `probabilistic_sampler` processors declaratively — and version those sampling decisions in Git so they're reviewable when you want to increase fidelity during an incident.

**Locking out non-technical contributors.** Product managers and analysts who used to iterate on dashboards in the UI are excluded by an all-code workflow. Grafana Git Sync's "edit in UI → auto-open a PR with screenshot diff" pattern is the practical middle path — audit trail without requiring CUE familiarity.

**Self-hosting Backstage solely for the observability catalog tab.** Roadie CEO David Tuite's January 2026 analysis found teams consistently report "6–12 months before they had something teams would actually use," and that "organizations that reported being happy with their self-hosted deployment had at least three dedicated engineers." If the goal is surfacing service dashboards and SLOs, use managed Backstage (Roadie, Spotify Enterprise) or a lighter IDP (Port, Cortex) rather than building a platform team to run it.

## Where to Start

**Stage 1 — Foundations (weeks 1–6).** Stand up a single Git repo for observability artifacts. Pick one critical service and codify its alerts as `PrometheusRule` CRDs or your SaaS Terraform provider. Add `promtool test rules` unit tests in CI. Standardize on OTel SDKs and ship a declarative `OTEL_CONFIG_FILE` alongside the binary. Benchmark: all alert changes for that service flow through PRs; no UI edits in 30 days.

**Stage 2 — Dashboards and SLOs (months 2–4).** Adopt the Grafana Foundation SDK or Perses for new dashboards. Enable Grafana Git Sync if you run Grafana 12+. Generate dashboards and alert rules from a service-template module — every new microservice gets the bundle automatically. Deploy Sloth or Pyrra; convert your five most critical services from ad-hoc alert thresholds to SLO error-budget burn alerts. Benchmark: >80% of new dashboards and alerts are code-first.

**Stage 3 — Pipelines and synthetics (months 4–8).** Centralize OTel Collector configurations in Git. Tier traffic using `routing` and `tail_sampling` processors and promote configs through dev/staging/prod. Add synthetic monitoring (Checkly or vendor equivalent) for top user journeys; write checks in TypeScript/Playwright and run them both in PR CI and as scheduled production monitors. Benchmark: all production services emit OTLP; synthetic checks gate deployments.

**Stage 4 — Optimization (months 8+).** Enforce `runbook_url` annotations, severity taxonomies, and ownership labels via OPA/conftest in CI. Run nightly `terraform plan` drift-detection jobs that alert on out-of-band UI edits. Apply Collector-side filtering and aggregation for cost control — version those decisions so they're reviewable. Migrate remaining Jsonnet Mixins to the Perses Go SDK or Foundation SDK where community-maintained equivalents exist.

For teams under 10 engineers running a single SaaS observability platform: skip Kubernetes-native CRDs entirely and stick to Terraform plus the provider's UI for low-criticality artifacts. If alert fatigue is your dominant pain, prioritize SLO-burn alerting and CI-tested rules over expanding dashboard coverage — more dashboards do not reduce noise.

<!-- TODO: Add detailed how-to for promtool test rules: input_series format, eval_time syntax, and asserting absent alerts — this is the most underused piece of the OaC toolchain -->
<!-- TODO: Add worked example of a Sloth PrometheusServiceLevel resource for a standard HTTP API: SLO window, error ratio SLI, and the generated multi-window alerts -->
<!-- TODO: Add Grafana Foundation SDK snippet (TypeScript or Go) showing a minimal dashboard build and deploy via gcx CLI -->

## See Also

- [SLOs and Error Budgets](/guides/slos-and-error-budgets/) — the SLO fundamentals that SLO-as-code tooling (Sloth, Pyrra, OpenSLO) builds on
- [Infrastructure Tagging for Observability](/guides/infrastructure-tagging-for-observability/) — OPA policy enforcement for the tags that OaC artifacts depend on
- [OTel Resource Attributes and Service Naming](/guides/otel-resource-attributes-and-service-naming/) — the resource attribute conventions that observability-as-code deployments propagate automatically
- [Building Observability Standards](/guides/building-observability-standards/) — the governance layer that OaC tooling enforces mechanically
- [CI/CD Pipeline Observability](/guides/cicd-pipeline-observability/) — instrumenting the pipelines that deploy observability artifacts
