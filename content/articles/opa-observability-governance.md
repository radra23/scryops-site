---
title: "Your Tagging Standard Is a Wiki Page. That's Why It Doesn't Work."
date: 2026-06-15
draft: false
excerpt: "Every team has a tagging standard. Most of them live in a wiki, enforced by nobody, remembered by almost nobody, and invisible to the CI pipeline entirely. Open Policy Agent fixes the root cause."
readtime: 6
tags: ["Observability", "Compliance", "CI/CD", "Best Practices", "Operations"]
---

> "A policy that lives only in documentation is not a policy. It is a wish."
> — Anonymous

Every observability platform eventually drowns in its own tags.

Someone, early on, wrote the standards. `environment: prod`. `owner: payments-team`. `monitoring-tier: tier1`. The document was thorough, organized, and immediately put in a wiki where it aged in peace. Six months later, half your infrastructure has no owner tag. Your cost reports attribute 40% of spend to "unknown." An alert fires at 2am and the runbook URL is missing, so the on-call engineer spends twenty minutes finding the right Slack channel to yell in.

This is not a compliance problem. It is an enforcement problem. The standard exists. The machine that enforces it does not.

## The Gap Between Policy and Passport

Think of observability tags as the passport system for your infrastructure. Every resource that enters production needs a valid passport — who owns it, what it costs, how critical it is, where to route an alert about it. Without that passport, your monitoring system has data but no context to act on.

The traditional approach is to ask engineers to stamp their own passports. You write the rules down, put them in onboarding docs, and add a checklist item to the deployment runbook. This works for a while, for teams small enough that the person who wrote the standard is also the person doing the deployments.

At scale, it fails reliably. Not because engineers are careless — because remembering is a tax on attention, and attention is finite.

Open Policy Agent turns the standard from a request into a constraint. Instead of "please add these tags," your CI pipeline says "here is the plan for what you are about to deploy, and here is OPA's verdict on whether it is allowed." Enforcement happens before anything touches production, and it happens the same way every time.

## What OPA Actually Does Here

OPA is a general-purpose policy engine. You write policies in a language called Rego, feed it the infrastructure plan you are about to apply, and it evaluates whether that plan satisfies your rules. If it does not, the pipeline stops.

The critical insight is *where* enforcement happens. Most teams, when they first think about tag governance, imagine auditing what is already running — scanning existing resources, finding violations, filing tickets. That treats the symptom. Resources without tags are already in production. Remediating them is a negotiation.

The more powerful gate is pre-deployment. A Terraform plan is a JSON document describing every resource you are about to create or modify. OPA can read that document before `terraform apply` runs and reject anything that does not meet policy. A resource without an owner tag never enters production in the first place.

{{< mermaid >}}
sequenceDiagram
    participant Dev as Developer
    participant CI as CI Pipeline
    participant OPA as OPA / Conftest
    participant Infra as Infrastructure

    Dev->>CI: Push infrastructure change
    CI->>CI: terraform plan → plan.json
    CI->>OPA: conftest verify --policy policies/ plan.json
    alt Policy passes
        OPA-->>CI: ✓ All resources compliant
        CI->>Infra: terraform apply
    else Policy fails
        OPA-->>CI: ✗ Missing: owner, monitoring-tier
        CI-->>Dev: PR blocked — fix tags before merging
    end
{{< /mermaid >}}

The tool that connects OPA to your Terraform plan is `conftest`. It takes your Rego policies and runs them against structured input — in this case, the JSON representation of a Terraform plan. The integration is a handful of CI steps:

```yaml
- name: Generate plan
  run: |
    terraform plan -out=plan.tfplan
    terraform show -json plan.tfplan > plan.json

- name: Enforce tag policy
  run: conftest verify --policy policies/ plan.json
```

That is the whole mechanism. Rego defines what "valid" means. Conftest applies it. The pipeline stops if anything fails.

## Where Things Break First

Here is the part that gets left out of most OPA guides.

**Vacuous tests pass silently.** The `opa test` command runs your policy unit tests. If you have no test files, it passes immediately and prints nothing. A CI step that runs `opa test policies/` with no `_test.rego` files looks green and is testing nothing. Write at least one test per policy rule — the pattern is to inject a synthetic resource as input and assert whether the policy fires. A mandatory-tags policy without a test case for a missing `owner` tag is a policy you cannot trust.

**`opa fmt --diff` does not fail CI without `--fail`.** If you add a formatting check to your pipeline, it needs `opa fmt --diff --fail {}` to actually block on violations. Without the flag it exits 0 regardless of what it finds. This is easy to miss because the command looks like it is checking something.

**The policy and the application code diverge.** A common production failure: the OPA policy expects `dotnet-version: "8.0"` but the application emits `Environment.Version.ToString()`, which resolves to `"8.0.11"`. The infrastructure tag passes validation because it is set in the Dockerfile as a hardcoded string. The telemetry tag fails silently because the runtime code does not match. Solve this in the policy by validating major-version prefix (`startswith(tags["dotnet-version"], "8.")`) instead of exact equality, and document the decision so the next person who reads the policy understands why the rule is written that way.

**OPA server's `/logs` endpoint does not exist.** Decision logs in OPA are pushed outward to a configured remote service via the `decision_logs.service` block in `opa-config.yaml` — they are not available via a GET request on the OPA server itself. Any compliance collector that tries `GET /logs` will get a 404. Build your log collection around OPA's push-based log forwarding, not a polling pattern.

{{< insight >}}
**The minimal viable start.** Write one policy file that requires four tags: `environment`, `application`, `owner`, and `monitoring-tier`. Write one test file that asserts a resource without `owner` fails. Wire `conftest verify` into the PR pipeline for one team. Get one deployment blocked by a missing tag, fix it visibly, and move on. Policy surface area grows later. The habit forms now.
{{< /insight >}}

## The Centralisation Trade-Off

A centralized OPA server cluster — where all teams call a shared policy API — is tempting. Single source of truth, centralized decision logs, org-wide compliance dashboards. Those things are worth having, eventually.

The operational cost is real and frequently underestimated. A bundle server needs to stay up for CI pipelines to function. A two-replica bundle server deployment with a `ReadWriteOnce` PersistentVolume will fail on multi-node clusters because both pods compete for the same volume — `ReadWriteMany` or an object store is the right backing for shared bundles. The OPA image variant matters too: `openpolicyagent/opa:x.x.x-envoy` bundles Envoy proxy integration for service mesh sidecar deployments and is not what you want for a standalone policy server.

Start simpler. Ship the Rego files in the same repository as your infrastructure code and run `conftest` locally. No cluster required, no bundle server to operate, no distributed failure modes. A centralised server becomes worth its overhead after the policies are stable, well-tested, and the team count grows past the point where per-repo policy copies drift from one another.

## What You Are Actually Building

The goal is not perfect tag coverage across every resource in production. The goal is a system where missing coverage shows up as a failed PR rather than a missed alert at 3am.

OPA makes that possible because it moves the policy out of the wiki and into the pipeline. The standards do not change — they acquire teeth. Violations are cheap to catch before a resource exists and expensive to remediate after it does. And the on-call engineer who wakes up to a firing alert at least knows who owns the service, how critical it is, and where the runbook lives — because no service could have been deployed without proving those things first.

That is what good observability context feels like: infrastructure that arrives with its passport already stamped.
