---
title: "Infrastructure Tagging for Observability: Policy-Driven Context at Scale"
date: 2026-06-12
draft: true
excerpt: "Consistent infrastructure tags are what make your observability stack's filter dropdowns useful. This guide covers the universal tagging schema, OPA policy enforcement, and wiring tags into OTel resource attributes across .NET services and IaC toolchains."
readtime: 9
tags: ["Observability", "OpenTelemetry", "CI/CD", "Best Practices", "Compliance"]
---

Observability tools are only as useful as the context they can filter on. A metric spike is a number until you can ask "which environment?", "which team?", "which service tier?" Infrastructure tags are the answer — but only when they're consistent, enforced, and connected to the signals your backend actually receives.

The pattern that makes this work: define a canonical tag schema, enforce it at deploy time with OPA policies, and wire the tag values into OTel resource attributes so every trace, metric, and log record inherits them automatically. Tags set in Terraform propagate to the service process via environment variables; the OTel SDK attaches them to every signal without manual enrichment on each call.

This guide covers the full path: schema → policy → IaC tooling → service-level integration.

## Universal Tagging Schema

A schema that covers observability routing, cost allocation, compliance scope, and stack metadata:

```yaml
# Observability and operational context
observability:
  environment:         [dev, test, staging, prod]
  application:         "business-application-name"
  component:           "microservice-or-component-name"
  owner:               "team-name-or-team@example.com"
  cost-center:         "financial-tracking-code"
  data-classification: [public, internal, confidential, restricted]

operational:
  monitoring-tier:     [tier1, tier2, tier3]   # tier1=critical/PagerDuty, tier3=Slack-only
  alert-routing:       "team-or-oncall-queue-identifier"
  backup-required:     [true, false]
  dr-required:         [true, false]

technical:
  managed-by:          [terraform, cdktf, cloudformation, helm, manual]
  stack-type:          [dotnet, java, python, nodejs, go, rust]
  deployment-method:   [container, vm, serverless, kubernetes]

governance:
  compliance-scope:    [sox, pci, hipaa, gdpr, none]
  retention-period:    "days-as-integer-string"
  encryption-required: [true, false]
```

`monitoring-tier` is the tag that drives alert routing decisions downstream. `alert-routing` connects a resource to the right team queue in your on-call tool without hard-coding team names in the alerting rules themselves.

{{< mermaid >}}
flowchart LR
    A["IaC Resource<br/>(Terraform / Helm)"]
    B["Env Var Injection<br/>OTEL_RESOURCE_ATTRIBUTES<br/>=deployment.environment=prod"]
    C["OTel ResourceBuilder<br/>attaches attributes<br/>to SDK on startup"]
    D["Every Signal<br/>trace · metric · log"]
    E["Backend Index<br/>dashboard filter<br/>by environment, team, tier"]

    A -->|"tag defined<br/>in code"| B
    B -->|"ResourceDetector<br/>reads on startup"| C
    C -->|"attribute on<br/>every export"| D
    D -->|"indexed field"| E
{{< /mermaid >}}

## OPA Policy Implementation

OPA evaluates tags before deployment. The core mandatory tag policy using modern `import rego.v1` syntax:

```rego
package tags.mandatory

import rego.v1

mandatory_tags := {
    "environment",
    "application",
    "component",
    "owner",
    "cost-center",
    "monitoring-tier",
    "managed-by"
}

valid_environments := {"dev", "test", "staging", "prod"}
valid_tiers        := {"tier1", "tier2", "tier3"}
valid_managed_by   := {"terraform", "cdktf", "cloudformation", "helm", "manual"}

has_mandatory_tags(resource) if {
    resource_tags := object.get(resource, "tags", {})
    missing_tags  := mandatory_tags - object.keys(resource_tags)
    count(missing_tags) == 0
}

valid_tag_values(resource) if {
    tags := object.get(resource, "tags", {})
    tags.environment         in valid_environments
    tags["monitoring-tier"]  in valid_tiers
    tags["managed-by"]       in valid_managed_by
    # Accept kebab-case team name ("payments-team") or email format
    regex.match(
        `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$|^[a-z-]+$`,
        tags.owner)
}

allow if {
    has_mandatory_tags(input.resource)
    valid_tag_values(input.resource)
}

violations contains msg if {
    not has_mandatory_tags(input.resource)
    resource_tags := object.get(input.resource, "tags", {})
    missing_tags  := mandatory_tags - object.keys(resource_tags)
    msg := sprintf("Missing mandatory tags: %v", [missing_tags])
}

violations contains msg if {
    has_mandatory_tags(input.resource)
    not valid_tag_values(input.resource)
    msg := "Invalid tag values — check environment, monitoring-tier, managed-by, and owner format"
}
```

`violations contains msg` uses OPA's incremental rule syntax: each rule appends to the `violations` set independently, so multiple failure reasons are all reported rather than stopping at the first.

### Stack-Specific Extension: .NET

A separate package extends the mandatory policy with .NET-specific tags, evaluated only when `stack-type == "dotnet"`:

```rego
package tags.dotnet

import rego.v1

dotnet_mandatory_tags := {"dotnet-version", "framework-type", "deployment-model"}

valid_dotnet_versions   := {"6.0", "7.0", "8.0"}
valid_frameworks        := {"core", "framework", "native-aot"}
valid_deployment_models := {"iis", "kestrel", "container", "serverless"}

dotnet_compliant(resource) if {
    tags := object.get(resource, "tags", {})
    tags["stack-type"] == "dotnet"
    # Set intersection: all dotnet_mandatory_tags must appear in the resource's tag keys
    present := object.keys(tags) & dotnet_mandatory_tags
    count(present) == count(dotnet_mandatory_tags)
    tags["dotnet-version"]   in valid_dotnet_versions
    tags["framework-type"]   in valid_frameworks
    tags["deployment-model"] in valid_deployment_models
}

# Default values used by auto-remediation pipelines (not enforced by this policy)
default_dotnet_tags := {
    "dotnet-version":     "8.0",
    "framework-type":     "core",
    "deployment-model":   "container",
    "runtime-identifier": "linux-x64"
}
```

`object.keys(tags) & dotnet_mandatory_tags` is set intersection in Rego — it returns the tags that are both present in the resource and required by the .NET policy.

## OTel .NET Integration

Map infrastructure tags to OTel resource attributes so they propagate to every trace, metric, and log record the service emits. Read tag values from environment variables injected by the orchestrator — this code runs once at service startup, not on each log event or request:

```csharp
var resourceBuilder = ResourceBuilder.CreateDefault()
    .AddService(
        serviceName:    Environment.GetEnvironmentVariable("APPLICATION") ?? "unknown",
        serviceVersion: Environment.GetEnvironmentVariable("VERSION")     ?? "0.0.0")
    .AddAttributes(new Dictionary<string, object>
    {
        ["deployment.environment"] = Environment.GetEnvironmentVariable("ENVIRONMENT")      ?? "dev",
        ["team.name"]              = Environment.GetEnvironmentVariable("OWNER")            ?? "unknown",
        ["team.cost_center"]       = Environment.GetEnvironmentVariable("COST_CENTER")      ?? "default",
        // Use string literal — opentelemetry.sdk.resources does not export SERVICE_VERSION
        ["service.version"]        = Environment.GetEnvironmentVariable("VERSION")          ?? "0.0.0",
        ["monitoring.tier"]        = Environment.GetEnvironmentVariable("MONITORING_TIER")  ?? "tier3",
        ["stack.type"]             = "dotnet",
        ["deployment.method"]      = Environment.GetEnvironmentVariable("DEPLOYMENT_MODEL") ?? "container",
    });

builder.Services.AddOpenTelemetry()
    .WithTracing(b => b
        .SetResourceBuilder(resourceBuilder)
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddOtlpExporter())
    .WithMetrics(b => b
        .SetResourceBuilder(resourceBuilder)
        .AddAspNetCoreInstrumentation()
        .AddOtlpExporter())
    .WithLogging(b => b
        .SetResourceBuilder(resourceBuilder)
        .AddOtlpExporter());
```

Resource attributes are attached to the SDK's `Resource` object once and propagate to every signal automatically — you do not need to add `deployment.environment` or `team.name` individually to spans, counters, or log scopes.

For Serilog, the same env vars become enrichment properties on every structured log record:

```csharp
Log.Logger = new LoggerConfiguration()
    .Enrich.WithProperty("environment",     Environment.GetEnvironmentVariable("ENVIRONMENT"))
    .Enrich.WithProperty("application",     Environment.GetEnvironmentVariable("APPLICATION"))
    .Enrich.WithProperty("component",       Environment.GetEnvironmentVariable("COMPONENT"))
    .Enrich.WithProperty("owner",           Environment.GetEnvironmentVariable("OWNER"))
    .Enrich.WithProperty("monitoring_tier", Environment.GetEnvironmentVariable("MONITORING_TIER"))
    .Enrich.WithProperty("stack_type",      "dotnet")
    // Wrap every sink in Async to decouple log emission from the request path
    .WriteTo.Async(a => a.Console(new JsonFormatter()))
    .WriteTo.Async(a => a.OpenTelemetry())
    .CreateLogger();
```

`WithProperty` calls are evaluated once at `LoggerConfiguration` time. The env var values are captured and stored as constants in the enricher — not re-read on each log call. Use only non-sensitive deployment metadata here: team name, environment, monitoring tier. Never read credential or secret env vars through this path.

A matching Dockerfile that provides development defaults while accepting production values from the orchestrator:

```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app

# Non-sensitive deployment metadata — overridden by orchestrator in production.
# In k8s, inject from the Downward API or ConfigMap; in ECS, from task definition env.
ENV ENVIRONMENT=dev
ENV APPLICATION=payment-service
ENV COMPONENT=payment-api
ENV OWNER=payments-team
ENV COST_CENTER=eng-payments-001
ENV MONITORING_TIER=tier1
ENV DEPLOYMENT_MODEL=container
ENV MANAGED_BY=kubernetes

COPY publish/ .
ENTRYPOINT ["dotnet", "PaymentService.dll"]
```

{{< insight lightbulb >}}
`Environment.Version.ToString()` returns the CLR runtime version string (e.g., `"8.0.4.0"`), not the .NET SDK version identifier (`"8.0"`). For the `service.version` resource attribute, prefer reading from an application-specific env var (`VERSION`, `APP_VERSION`, or similar) injected by your CI pipeline rather than deriving it from the runtime.
{{< /insight >}}

## Terraform Module

A module that enforces the mandatory tag set and conditionally adds .NET-specific tags when `stack_type = "dotnet"`:

```hcl
# modules/tagged-resource/main.tf
locals {
  mandatory_tags = {
    environment       = var.environment
    application       = var.application
    component         = var.component
    owner             = var.owner
    "cost-center"     = var.cost_center
    "monitoring-tier" = var.monitoring_tier
    "managed-by"      = "terraform"
  }

  dotnet_tags = var.stack_type == "dotnet" ? {
    "stack-type"       = "dotnet"
    "dotnet-version"   = var.dotnet_version
    "framework-type"   = var.framework_type
    "deployment-model" = var.deployment_model
  } : {}

  # Consumer-supplied tags overlay the base set, allowing targeted overrides
  final_tags = merge(local.mandatory_tags, local.dotnet_tags, var.additional_tags)
}

resource "aws_instance" "example" {
  ami           = var.ami_id
  instance_type = var.instance_type
  tags          = local.final_tags
}

variable "stack_type" {
  description = "Technology stack type"
  type        = string
  validation {
    condition     = contains(["dotnet", "java", "python", "nodejs", "go", "rust"], var.stack_type)
    error_message = "stack_type must be one of: dotnet, java, python, nodejs, go, rust."
  }
}

variable "dotnet_version" {
  description = ".NET version — required when stack_type is dotnet"
  type        = string
  default     = "8.0"
  validation {
    # Cross-variable validation: the condition is only enforced when stack_type is dotnet.
    # When stack_type != dotnet, the condition short-circuits to true.
    condition     = var.stack_type != "dotnet" || contains(["6.0", "7.0", "8.0"], var.dotnet_version)
    error_message = ".NET version must be 6.0, 7.0, or 8.0."
  }
}
```

`merge()` processes left-to-right with rightmost values winning. `var.additional_tags` overrides `local.dotnet_tags` which overrides `local.mandatory_tags` — callers can override dotnet defaults but the mandatory tags can be reclaimed by putting them outside the merge if you need them to be non-overridable.

## CDKTF Aspects for Auto-Tagging

CDKTF Aspects apply tags uniformly to every taggable construct in a stack without modifying individual resource definitions. Any resource added to the stack later automatically inherits the tags:

```typescript
import { Construct, IConstruct } from "constructs";
import { Aspects, IAspect } from "cdktf";

interface TaggingConfig {
  environment:    string;
  application:    string;
  component:      string;
  owner:          string;
  costCenter:     string;
  monitoringTier: "tier1" | "tier2" | "tier3";
  stackType?:     "dotnet" | "java" | "python" | "nodejs" | "go" | "rust";
  dotnetVersion?: "6.0" | "7.0" | "8.0";
  frameworkType?: "core" | "framework" | "native-aot";
}

export class UniversalTaggingAspect implements IAspect {
  constructor(private config: TaggingConfig) {}

  visit(node: IConstruct): void {
    if (!this.isTaggableConstruct(node)) return;

    const baseTags: Record<string, string> = {
      environment:       this.config.environment,
      application:       this.config.application,
      component:         this.config.component,
      owner:             this.config.owner,
      "cost-center":     this.config.costCenter,
      "monitoring-tier": this.config.monitoringTier,
      "managed-by":      "cdktf",
    };

    const stackTags =
      this.config.stackType === "dotnet"
        ? {
            "stack-type":     "dotnet",
            "dotnet-version": this.config.dotnetVersion ?? "8.0",
            "framework-type": this.config.frameworkType ?? "core",
          }
        : {};

    // Existing tags on the resource take precedence over the base set,
    // allowing individual resources to override while still getting defaults.
    const existingTags = (node as any).tagsInput ?? {};
    (node as any).tags = { ...baseTags, ...stackTags, ...existingTags };
  }

  private isTaggableConstruct(node: IConstruct): boolean {
    return "tagsInput" in node || "tags" in node;
  }
}

// Wire into a stack — typically in the stack constructor
Aspects.of(this).add(new UniversalTaggingAspect({
  environment:    "prod",
  application:    "payment-service",
  component:      "api-gateway",
  owner:          "platform-team",
  costCenter:     "engineering-001",
  monitoringTier: "tier1",
  stackType:      "dotnet",
  dotnetVersion:  "8.0",
  frameworkType:  "core",
}));
```

## CI/CD Enforcement with conftest

[conftest](https://www.conftest.dev/) evaluates OPA policies against Terraform plans in a GitHub Actions pipeline, failing the PR before any resource is created with non-compliant tags:

```yaml
name: Tag Policy Validation
on:
  pull_request:
    paths: ["infrastructure/**"]

jobs:
  tag-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup OPA
        uses: open-policy-agent/setup-opa@v2
        with:
          version: latest

      - name: Install conftest
        run: |
          wget -qO- https://github.com/open-policy-agent/conftest/releases/latest/download/conftest_Linux_x86_64.tar.gz \
            | tar xz -C /usr/local/bin

      - name: Terraform plan
        working-directory: infrastructure
        run: |
          terraform init
          terraform plan -out=plan.tfplan
          terraform show -json plan.tfplan > plan.json

      - name: Validate tags with OPA
        run: |
          conftest verify --policy policies/ infrastructure/plan.json \
            --output json > tag-report.json || true

      - name: Fail on violations
        run: |
          violations=$(jq '[.[].failures // []] | add | length' tag-report.json)
          if [ "$violations" -gt 0 ]; then
            echo "Tag policy violations: $violations"
            jq -r '.[].failures[].msg' tag-report.json
            exit 1
          fi

      - name: Post violations to PR
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require("fs");
            const report = JSON.parse(fs.readFileSync("tag-report.json", "utf8"));
            const failures = report.flatMap(r => r.failures ?? []);
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner:        context.repo.owner,
              repo:         context.repo.repo,
              body: [
                "## Tag validation failed",
                "",
                ...failures.map(f => `- ${f.msg}`)
              ].join("\n")
            });
```

The `conftest verify` step exits non-zero on policy violations. The jq step counts failures and surfaces them to the log; the GitHub script step posts the specific messages to the PR comment thread.

<!-- TODO: Add drift detection section — polling cloud provider resource APIs (AWS Resource Groups Tagging API, Azure Resource Graph, GCP Asset Inventory) to find manually-created or legacy resources that bypassed IaC, then evaluating their tag sets against the OPA policy and filing remediation tickets -->
<!-- TODO: Add Kubernetes admission webhook integration using OPA Gatekeeper ConstraintTemplate or Kyverno ClusterPolicy for enforcing tags on Namespace and Pod resources at admission time -->

## See Also

- [OTel Resource Attributes and Service Naming](/guides/otel-resource-attributes-and-service-naming/) — the complete reference for service identity in OTel resource attributes
- [Log Context Enrichment](/guides/log-context-enrichment/) — how resource attribute tags propagate into structured log records via three-tier enrichment
- [Structured Logging in .NET](/howtos/implement-structured-logging-dotnet/) — the Serilog and ILogger patterns this guide's enrichment integrates with
- [CI/CD Pipeline Observability](/guides/cicd-pipeline-observability/) — broader observability treatment for the deployment pipeline
