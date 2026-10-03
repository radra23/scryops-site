---
title: "Your Tagging Standard Is a Wiki Page. That's Why It Doesn't Work."
date: 2026-09-29
draft: false
excerpt: "Every team has a tagging standard. Most of them live in a wiki, enforced by nobody, remembered by almost nobody, and invisible to the CI pipeline. Open Policy Agent fixes the root cause."
readtime: 7
tags: ["Observability", "Compliance", "CI/CD", "Best Practices", "Operations"]
---

Every observability platform eventually drowns in its own tags.

Someone, early on, wrote the standards. `environment: prod`. `owner: payments-team`. `monitoring-tier: tier1`. The document was thorough, organised, and promptly filed in a wiki where it aged in peace. Six months later, half your infrastructure has no owner tag. Your cost reports pin a big share of spend on "unknown". An alert fires at 2am, the runbook URL is missing, and the on-call engineer spends twenty minutes hunting for the right Slack channel to yell in.

This isn't a compliance problem. It's an enforcement problem. The standard exists. The machine that enforces it doesn't.

## The Gap Between Policy and Passport

Think of observability tags as the passport system for your infrastructure. Every resource that enters production needs a valid passport: who owns it, what it costs, how critical it is, and where to route an alert about it. Without one, your monitoring system has data but no context to act on.

The traditional approach asks engineers to stamp their own passports. You write the rules down, put them in the onboarding docs, and add a checklist item to the deployment runbook. That works for a while, as long as the team is small enough that the person who wrote the standard is also the person deploying.

At scale, it fails reliably. Not because engineers are careless, but because remembering is a tax on attention, and attention runs out.

Open Policy Agent turns the standard from a request into a constraint. Instead of "please add these tags", your CI pipeline says "here's the plan for what you're about to deploy, and here's OPA's verdict on whether it's allowed". Enforcement happens before anything touches production, and it happens the same way every time.

## What OPA Actually Does Here

OPA is a general-purpose policy engine. You write policies in a language called Rego, feed it the infrastructure plan you're about to apply, and it checks whether that plan follows your rules. If it doesn't, the pipeline stops.

The critical insight is *where* the check happens. Most teams, when they first think about tag governance, picture auditing what's already running: scanning resources, finding violations, filing tickets. That treats the symptom. The untagged resources are already in production, and getting them fixed is a negotiation.

The stronger gate is before deployment. A Terraform plan can be exported as a JSON document describing every resource you're about to create or change. OPA can read that document before `terraform apply` runs and reject anything that breaks policy. A resource without an owner tag never reaches production in the first place.

{{< mermaid >}}
sequenceDiagram
    participant Dev as Developer
    participant CI as CI Pipeline
    participant OPA as OPA / Conftest

    Dev->>CI: push infra change
    CI->>CI: terraform plan → plan.json
    CI->>OPA: conftest test plan.json
    alt Policy passes
        OPA-->>CI: pass: all compliant
        CI->>CI: terraform apply
    else Policy fails
        OPA-->>CI: fail: missing tags
        Note over CI,OPA: owner, monitoring-tier
        CI-->>Dev: PR blocked
        Note over Dev,CI: fix tags before merging
    end
{{< /mermaid >}}

Here's the whole rule, in current Rego syntax. It checks every resource being created or updated that has a `tags` attribute, and names the tags that are missing:

```rego
package main

import rego.v1

required_tags := {"environment", "application", "owner", "monitoring-tier"}

deny contains msg if {
	some rc in input.resource_changes
	some action in rc.change.actions
	action in {"create", "update"}
	"tags" in object.keys(rc.change.after)
	present := {key | some key, _ in object.get(rc.change.after, "tags", {})}
	missing := required_tags - present
	count(missing) > 0
	msg := sprintf("%s is missing tags: %v", [rc.address, sort(missing)])
}
```

Resources that can't carry tags, like an IAM policy attachment, have no `tags` attribute, so the rule skips them instead of failing every plan. If you set tags through the AWS provider's `default_tags`, check `tags_all` instead of `tags`, or the rule won't see them.

The tool that connects the policy to your plan is `conftest`. It runs Rego policies against structured files, in this case the JSON version of a Terraform plan. The integration is a handful of CI steps:

```yaml
- name: Generate plan
  run: |
    terraform plan -out=plan.tfplan
    terraform show -json plan.tfplan > plan.json

- name: Test the policies
  run: conftest verify --policy policies/

- name: Enforce tag policy
  run: conftest test --policy policies/ plan.json
```

Mind the two subcommands. `conftest verify` runs your policy's unit tests. `conftest test` checks the plan. Swap them and you get a quiet disaster: `conftest verify --policy policies/ plan.json` ignores `plan.json` completely, runs the tests, and exits green on a plan full of untagged resources.

That's the whole mechanism. Rego defines what "valid" means. Conftest applies it. The pipeline stops if anything fails.

## Where Things Break First

Here's the part most OPA guides leave out.

**Missing tests pass silently.** `opa test` runs your policy unit tests. If there are no test files, it prints nothing and exits 0. A CI step that runs `opa test policies/` with no `_test.rego` files looks green and tests nothing. Write at least one test per rule. The pattern is to feed the policy a synthetic resource and assert what it decides:

```rego
package main

import rego.v1

test_missing_owner_is_denied if {
	deny["aws_s3_bucket.logs is missing tags: [\"owner\"]"] with input as {"resource_changes": [{
		"address": "aws_s3_bucket.logs",
		"change": {"actions": ["create"], "after": {"tags": {
			"environment": "prod",
			"application": "checkout",
			"monitoring-tier": "tier1",
		}}},
	}]}
}
```

A mandatory-tags policy without a test for a missing `owner` is a policy you can't trust.

**`opa fmt --diff` doesn't fail CI without `--fail`.** If you add a formatting check to your pipeline, run `opa fmt --diff --fail policies/`. Without the flag, it exits 0 whatever it finds. It's easy to miss, because the command looks like it's checking something.

**The plan and the running service disagree.** OPA can only judge what's in the plan. Say your policy requires a `dotnet-version` tag and the Terraform sets it to `"8.0"`. The plan passes. But the service's own telemetry reports `Environment.Version`, which comes out as `"8.0.11"`, and any dashboard that joins the two never matches. Conftest can't see that, because runtime telemetry isn't in the plan. Agree on one format (major version only, say), check the tag against it with something like `startswith(tags["dotnet-version"], "8.")` instead of exact equality, and check what the service actually emits somewhere that can see it, such as a test against its telemetry or a rule in your Collector.

**An OPA server has no `/logs` endpoint.** OPA pushes decision logs out to a remote service you configure in the `decision_logs` section of its config. It doesn't serve them over HTTP, so a compliance collector that polls `GET /logs` gets a 404. Build your log collection around OPA's push-based forwarding, not polling.

{{< insight >}}
**The minimal viable start.** Write one policy file that requires four tags: `environment`, `application`, `owner` and `monitoring-tier`. Write one test that proves a resource without `owner` fails. Wire `conftest test` into the PR pipeline for one team. Get one deployment blocked by a missing tag, fix it where everyone can see, and move on. The policy can grow later. The habit forms now.
{{< /insight >}}

## The Centralisation Trade-Off

A centralised OPA server cluster, where every team calls a shared policy API, is tempting. One source of truth, centralised decision logs, org-wide compliance dashboards. Those are worth having, eventually.

The running cost is real and often underestimated. Your CI pipelines now depend on the policy service staying up. OPA usually pulls its policy bundles over HTTP from an object store or a plain web server, so keep that store simple. If you do back a bundle server with a Kubernetes volume, a `ReadWriteOnce` volume can only be mounted read-write on one node, so two replicas scheduled on different nodes will fight over it. Use `ReadWriteMany` or an object store. And pick the right image: the `-envoy` tags of `openpolicyagent/opa` are OPA built with the Envoy external-authorisation plugin, meant to run beside Envoy in a service mesh. You don't want them for a standalone policy server.

Start simpler. Keep the Rego files in the same repository as your infrastructure code and run `conftest` in CI and on your laptop. No cluster, no bundle server to operate, no distributed failure modes. A central server earns its overhead once the policies are stable and well tested, and the team count has grown past the point where per-repo copies of the policy start drifting apart.

## What You're Actually Building

The goal isn't perfect tag coverage across every resource in production. The goal is a system where missing coverage shows up as a failed PR instead of a missed alert at 3am.

OPA makes that possible because it moves the policy out of the wiki and into the pipeline. The standards don't change. They just get teeth. A violation is cheap to catch before the resource exists and expensive to clean up after. And the on-call engineer who wakes up to a firing alert at least knows who owns the service, how critical it is and where the runbook lives, because nothing could have been deployed without proving those things first.

That's what good observability context feels like: infrastructure that arrives with its passport already stamped.
