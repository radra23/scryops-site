---
title: "OTel Resource Attributes: The Identity Layer of Your Telemetry"
date: 2026-06-10
draft: true
excerpt: "Every span, metric, and log your system emits needs to know what produced it. Resource attributes are how OpenTelemetry encodes that identity — service name, version, environment, cluster, namespace. Get them wrong and your telemetry is noise. Get them right and everything correlates automatically."
readtime: 8
tags: ["OpenTelemetry", "Observability", "Best Practices", "Kubernetes"]
---

Resource attributes are the metadata attached to every piece of telemetry your service produces. They answer the question: *who sent this?* Not which request, not which user — which service instance, running which version, in which environment, on which infrastructure.

Most teams underinvest here. They set `service.name` and call it done. Then at 3am they're looking at a span with no environment tag, no version, no cluster name, and no way to know whether it came from production or staging.

## The Required Baseline

The OpenTelemetry semantic conventions define a minimum viable identity for any service:

```yaml
service.name: "checkout-api"          # human-readable, unique within your org
service.namespace: "commerce"          # group of related services
service.version: "1.4.2"              # semver, matches your build tag
service.instance.id: "pod-xyz-123"    # unique per running instance
```

`service.name` is the most important. It must be:
- Consistent across deployments (not generated at runtime)
- Unique within your organisation
- Lowercase, hyphen-separated (not camelCase, not dots)
- Stable across releases — do not encode version in the name

`service.version` is the second most important. Without it you cannot answer "did this start after the deploy?"

## Deployment Context

Beyond the service identity, you need deployment context — where is this running?

```yaml
deployment.environment: "production"   # production | staging | development
```

This is the attribute you will filter on more than any other. Every dashboard, every alert, every SLO query starts with `deployment.environment = "production"`. If it is missing or inconsistent (`prod`, `production`, `PROD` all appearing in the same backend), your queries will miss data silently.

Enforce a closed vocabulary. Three values maximum: `production`, `staging`, `development`. Use an OTel Collector processor to enforce this at the pipeline level if you cannot trust application teams to set it correctly.

## Kubernetes Resource Attributes

For services running on Kubernetes, the `k8s.*` resource attributes are essential for correlating spans with infrastructure metrics and logs:

```yaml
k8s.cluster.name: "us-east-prod-01"
k8s.namespace.name: "commerce"
k8s.pod.name: "checkout-api-7d9f8b-xkv2p"
k8s.node.name: "ip-10-0-1-45.ec2.internal"
k8s.deployment.name: "checkout-api"
k8s.container.name: "checkout-api"
```

The OTel Collector's `k8sattributes` processor can inject these automatically from the Kubernetes API — you do not need to set them in application code. Configure it in your DaemonSet Collector and every span gets cluster context for free.

```yaml
processors:
  k8sattributes:
    auth_type: serviceAccount
    extract:
      metadata:
        - k8s.namespace.name
        - k8s.pod.name
        - k8s.node.name
        - k8s.deployment.name
```

## Cloud Provider Attributes

For cloud-hosted services, add cloud identity so you can correlate with cloud provider metrics:

```yaml
cloud.provider: "aws"                  # aws | azure | gcp
cloud.region: "us-east-1"
cloud.account.id: "123456789012"
cloud.availability_zone: "us-east-1a"
```

Like the Kubernetes attributes, these can be injected by the Collector's `resourcedetection` processor rather than set in application code.

## Naming Convention Rules

Consistent names are more valuable than descriptive names. Rules that matter:

**Service names:** `{team}-{function}` or `{domain}-{function}`. Examples: `commerce-checkout`, `auth-token`, `data-pipeline-ingest`. Avoid: `CheckoutService`, `checkout_api_v2`, `new-checkout`.

**Environments:** closed list, enforced. Three values maximum.

**Versions:** semver. Never `latest`, never a git SHA as the primary identifier (use `service.version` for semver, `vcs.repository.ref.revision` for the SHA).

**Namespaces:** domain or team boundary. Should match your Kubernetes namespace structure.

## Enforcing Standards at the Pipeline Level

The OTel Collector is your last line of defence before telemetry reaches storage. Use the `transform` processor to normalise values, and the `filter` processor to drop telemetry that still doesn't meet the bar:

```yaml
processors:
  transform:
    error_mode: ignore
    trace_statements:
      - context: resource
        statements:
          # Normalise environment values
          - set(attributes["deployment.environment"], "production")
            where attributes["deployment.environment"] == "prod"
          - set(attributes["deployment.environment"], "staging")
            where attributes["deployment.environment"] == "stg"
  filter/require_service_name:
    error_mode: ignore
    traces:
      span:
        # Drop spans with no service name
        - resource.attributes["service.name"] == nil
```

The `filter` processor drops any telemetry item matching its OTTL condition — that's the mechanism for rejection. Don't reach for `transform`'s `limit()` function here: it caps the *number* of attributes on a record (pruning down to N, with an optional priority list), it doesn't drop the record itself, so it can't reject anything on its own.

## The Self-Assessment Checklist

Before shipping a service, verify:

- [ ] `service.name` is set, lowercase, hyphen-separated, unique, stable
- [ ] `service.version` reflects the build version (not `latest`, not `unknown`)
- [ ] `service.namespace` groups this service with related services
- [ ] `deployment.environment` is set to exactly `production`, `staging`, or `development`
- [ ] Kubernetes attributes are injected by the Collector (`k8sattributes` processor)
- [ ] Cloud attributes are injected by the Collector (`resourcedetection` processor)
- [ ] Resource attributes are set once at SDK initialisation, not per-span

<!-- TODO: Add section on custom resource attributes for business context (team, cost-centre, product) -->
<!-- TODO: Add section on resource attribute cardinality limits (service.instance.id is high cardinality) -->
<!-- TODO: Add worked examples for Python, Go, Java SDK initialisation with resource attributes -->
