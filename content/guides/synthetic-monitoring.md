---
title: "Synthetic Monitoring: Proactive Testing for User Experience"
date: 2026-06-15
draft: true
excerpt: "Synthetic monitoring runs scripted checks on a schedule so failures surface before real users hit them. This guide covers the three check types, when to use each, how to scope monitoring frequency, and what synthetic monitoring is routinely misapplied to."
readtime: 7
tags: ["Observability", "Monitoring", "Reliability", "RUM"]
---

Synthetic monitoring is a proactive monitoring technique that simulates user interactions with your applications and services to detect issues before they impact real users. Unlike real user monitoring (RUM), which captures actual user experiences as they happen, synthetic monitoring runs scripted checks at regular intervals from controlled environments.

The key tradeoff: RUM shows what real users experience (representative, high volume, noisy). Synthetic monitoring shows what a scripted client experiences (deterministic, low volume, controllable). You need both — but they answer different questions.

## Check Types

**Browser monitors** are complex, browser-based tests that simulate complete user journeys: multi-step flows (login, search, checkout), form submissions, and UI functionality verification. These are the most expensive checks to run and the hardest to maintain as UIs change — reserve them for the flows where failures cost the most.

**API monitors** are lightweight checks that validate endpoints and service health: status code verification, response time measurement, payload validation. Faster and cheaper than browser monitors; appropriate for any service boundary with a defined contract.

**Simple monitors** are basic availability and reachability tests: ping, HTTP response validation, TCP port checks. These are not observability — they're availability detection. Useful at the very bottom of the stack but not a substitute for higher-level checks.

## Purpose

{{< mermaid >}}
graph TD
    A[Synthetic Monitoring] --> B[Proactive Detection]
    A --> C[Performance Benchmarking]
    A --> D[SLA Verification]
    A --> E[Business Transaction Validation]
    B --> F[Detect issues before users]
    C --> G[Track performance trends]
    D --> H[Verify uptime commitments]
    E --> I[Ensure critical functions work]
{{< /mermaid >}}

## Resource Considerations

Synthetic monitoring consumes resources in two dimensions. Each test generates real load on your systems — a browser monitor that simulates checkout hits your cart, payments, and inventory services just as a real user would. And each test consumes monitoring budget: more frequent, more complex checks cost proportionally more.

Scope your strategy against business priorities, not infrastructure topology. The goal is coverage of critical user journeys at appropriate frequency, not exhaustive coverage of every endpoint.

## Optimization Principles

1. **Focus on user journeys, not infrastructure checks.** A browser monitor on checkout matters. A ping on your load balancer is infrastructure monitoring — use a different tool.
2. **Reserve high-frequency checks for critical business functions.** A revenue-generating flow warrants a 1-minute check interval. An internal admin dashboard does not.
3. **Use specialized tools for infrastructure monitoring tasks.** Synthetic monitors are poor substitutes for node exporters, health-check endpoints, or infrastructure platforms.
4. **Calibrate frequency to criticality and stability.** A mature, rarely-changed API can run checks every 5 minutes. A newly deployed service under active development may need tighter intervals during rollout, then less.
5. **Consolidate related checks.** A single end-to-end browser monitor that covers login → search → add-to-cart is often better than three separate API checks of those same endpoints in isolation — the integrated test catches interaction failures the isolated checks miss.

## Common Misuses

Synthetic monitoring is frequently applied to tasks better handled by purpose-built tools:

- **Certificate monitoring** — Dedicated certificate management systems (cert-manager, Vault PKI, commercial platforms) track expiry against the actual certificate store. A synthetic monitor that checks TLS handshake success is an approximation; a dedicated tool that reads the certificate directly is authoritative.
- **Static content checks** — CDN monitoring and origin health checks are the right layer for verifying static asset availability.
- **Server health checks** — Infrastructure monitoring (Prometheus node exporter, cloud provider health APIs) is the right tool. Synthetic monitors can't distinguish "server is down" from "test environment can't reach server."
- **Continuous load testing** — Load testing tools (k6, Locust, Gatling) are designed for this. Synthetic monitors at high frequency to simulate load is an expensive misuse that produces unreliable results.

<!-- TODO: Add implementation section: writing Checkly checks in Playwright/TypeScript, deploying via CLI, running in CI -->
<!-- TODO: Add section on multi-region checks: understanding geographic baseline differences vs real failures -->
<!-- TODO: Add section on alert calibration: what failure counts justify paging vs recording, avoiding alert fatigue from transient network issues -->
<!-- TODO: Add worked example of SLA verification: mapping a 99.9% uptime SLO to synthetic check frequency and failure threshold -->
<!-- TODO: Verify attributed quotes before adding: source document included quotes attributed to Charity Majors (Honeycomb) and Baron Schwartz (VividCortex) — locate primary sources before using {{< quote_with_author >}} -->

## See Also

- [Certificate Monitoring](/guides/certificate-monitoring/) — purpose-built certificate expiry tracking, the canonical example of what synthetic monitoring should not be used for
- [RUM and Core Web Vitals](/guides/rum-and-core-web-vitals/) — the complementary signal: real user experience where synthetic monitoring covers controlled availability
- [SLOs and Error Budgets](/guides/slos-and-error-budgets/) — synthetic checks feed SLA verification; burn rate alerting applies to synthetic-derived availability SLOs
- [Observability as Code](/guides/observability-as-code/) — Checkly CLI for synthetic monitoring as code: checks in version control, running in CI and as production monitors
