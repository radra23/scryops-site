---
title: "OTel Resource Attributes: The Identity Layer of Your Telemetry"
date: 2026-11-16
draft: false
excerpt: "Every span, metric, and log needs to say what produced it. Resource attributes carry that identity: service name, version, environment, cluster. Here's the baseline to set, what the Collector can fill in for you, and how to enforce it."
readtime: 8
tags: ["OpenTelemetry", "Observability", "Best Practices", "Kubernetes"]
card:
  title: "Resource Attributes: Your Telemetry's Identity Layer"
---

Resource attributes are the metadata attached to every piece of telemetry your service produces. They answer one question: *who sent this?* Not which request, and not which user. Which service instance, running which version, in which environment, on which infrastructure.

Most teams underinvest here. They set `service.name` and call it done. Then at 3am they're staring at a span with no environment, no version, and no cluster name, and no way to tell whether it came from production or staging.

Attribute names and stability below are checked against semantic conventions **v1.45.0** (2 November 2026). The Collector configs follow the processor documentation for **otelcol-contrib v0.165.1**.

## The baseline

Four attributes identify a service, and all four are stable:

```yaml
service.name: "checkout-api"          # the logical service, same for every replica
service.namespace: "commerce"         # a group of related services
service.version: "1.4.2"              # matches your build tag
service.instance.id: "627cc493-f310-47de-96bd-71410b7dec09"   # unique per running instance
```

`service.name` matters most. The spec asks for two things: it's the same for every instance of a horizontally scaled service, and it's unique within its `service.namespace`. On top of that, we'd add three house rules:

- Set it in config, never generate it at runtime.
- Keep it lowercase and hyphen-separated, so nobody has to remember whether it was `CheckoutAPI` or `checkout_api`.
- Don't put the version in the name. That's what `service.version` is for.

If you set nothing, the SDK doesn't leave the name empty. It falls back to `unknown_service`, or `unknown_service:` plus the process name, such as `unknown_service:java`. That detail matters when you enforce the baseline later.

`service.version` comes second. Without it you can't answer "did this start after the deploy?"

`service.instance.id` tells replicas apart. The spec recommends a random UUID. Check whether your SDK generates one, because not all of them do by default. Using the pod name works, but the spec treats names like that as details you may not want to expose, and prefers an opaque ID.

### Setting them

The standard environment variables work in every SDK:

```bash
export OTEL_SERVICE_NAME="checkout-api"
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=1.4.2,deployment.environment.name=production"
```

There's no `OTEL_SERVICE_VERSION` variable. The version goes in `OTEL_RESOURCE_ATTRIBUTES` as `service.version`, or in the resource you build in code. Either way, a resource is fixed when the SDK starts. You set these once, not per span.

## Deployment context

After identity comes location. Where is this running?

```yaml
deployment.environment.name: "production"   # production | staging | development
```

The name changed. `deployment.environment` is deprecated, and the stable attribute is `deployment.environment.name`. Plenty of SDK versions, dashboards, and backends still use the old one, so check which name your queries filter on before you assume the data is missing.

You'll filter on this attribute more than any other. Every dashboard, alert, and SLO query starts with it. If the values drift (`prod`, `production`, and `PROD` all in the same backend), your queries miss data and nothing tells you.

So keep a closed list. Three values is plenty: `production`, `staging`, `development`. If you can't trust every team to stick to it, enforce it in the Collector. The config is further down.

## Kubernetes attributes

On Kubernetes, the `k8s.*` attributes tie your spans to infrastructure metrics and logs:

```yaml
k8s.cluster.name: "us-east-prod-01"
k8s.namespace.name: "commerce"
k8s.pod.name: "checkout-api-7d9f8b-xkv2p"
k8s.node.name: "ip-10-0-1-45.ec2.internal"
k8s.deployment.name: "checkout-api"
k8s.container.name: "checkout-api"
```

You don't set most of these in application code. The Collector's `k8s_attributes` processor looks up the pod that sent the telemetry and adds them. The processor used to be called `k8sattributes`. That name still works as a deprecated alias.

```yaml
processors:
  k8s_attributes:
    auth_type: serviceAccount
    filter:
      # DaemonSet mode: only watch pods on this Collector's own node
      node_from_env_var: KUBE_NODE_NAME
    extract:
      metadata:
        - k8s.namespace.name
        - k8s.pod.name
        - k8s.pod.uid
        - k8s.node.name
        - k8s.deployment.name
```

Three things that config doesn't do on its own:

- **It needs RBAC.** The Collector's service account needs `get`, `watch`, and `list` on pods and namespaces. Without them it has nothing to look up, and your telemetry passes through unchanged.
- **It needs `KUBE_NODE_NAME`.** Set it on the Collector container from `spec.nodeName` with the downward API. Without the node filter, every DaemonSet pod watches every pod in the cluster.
- **It doesn't know the cluster name.** `k8s.cluster.name` isn't something the Kubernetes API hands out, so this processor can't add it. Get it from the `resource_detection` processor (below) or set it yourself in the Collector's config, one value per cluster.

`k8s.container.name` is the other one that isn't free. In a pod with more than one container, the processor can only pick the right one if the telemetry already carries `container.id` or `k8s.container.name`.

## Cloud provider attributes

For cloud-hosted services, add cloud identity so you can line telemetry up with the provider's own metrics:

```yaml
cloud.provider: "aws"                  # aws | azure | gcp
cloud.region: "us-east-1"
cloud.account.id: "123456789012"
cloud.availability_zone: "us-east-1a"
```

These are still at development stability, so the names could change. They're also widely used, and no replacement has been proposed.

Like the Kubernetes attributes, they come from the Collector, not your code. The `resource_detection` processor (formerly `resourcedetection`, still accepted as an alias) asks the cloud's metadata service:

```yaml
processors:
  resource_detection:
    detectors: [env, eks]
    timeout: 15s
    override: false
    eks:
      resource_attributes:
        k8s.cluster.name:
          enabled: true
```

The cluster name is opt-in on EKS, as shown, and it only works on EC2-backed nodes with permission to call `ec2:DescribeInstances`. The GKE detector sets it by default.

One caveat: detection describes the machine the *Collector* runs on. That's right for a DaemonSet or sidecar, where the Collector shares a node with your service. It's wrong for a central gateway, which would stamp its own zone on everyone's telemetry.

## Naming rules

Consistent names beat descriptive names. These are our conventions, not the spec's, and the reason for each is the same: nobody should have to guess.

**Service names:** `{domain}-{function}` or `{team}-{function}`. Good: `commerce-checkout`, `auth-token`, `data-pipeline-ingest`. Avoid: `CheckoutService`, `checkout_api_v2`, `new-checkout`.

**Environments:** a closed list, enforced. Three values at most.

**Versions:** the version you'd put on a release, never `latest`. Keep the git SHA out of `service.version` and record it separately as `vcs.ref.head.revision`. That attribute replaced `vcs.repository.ref.revision` and is at release-candidate stability.

**Namespaces:** a domain or team boundary. Life is simpler when `service.namespace` matches your Kubernetes namespace layout.

## Enforcing it in the Collector

The Collector is the last stop before telemetry reaches storage. Use the `transform` processor to fix values you can fix, and the `filter` processor to drop what still doesn't meet the bar:

```yaml
processors:
  transform/normalise_env:
    error_mode: ignore
    trace_statements:
      # Carry the deprecated name over to the stable one
      - set(resource.attributes["deployment.environment.name"], resource.attributes["deployment.environment"]) where resource.attributes["deployment.environment.name"] == nil and resource.attributes["deployment.environment"] != nil
      # Normalise the values
      - set(resource.attributes["deployment.environment.name"], "production") where resource.attributes["deployment.environment.name"] == "prod"
      - set(resource.attributes["deployment.environment.name"], "staging") where resource.attributes["deployment.environment.name"] == "stg"
  filter/require_service_name:
    error_mode: ignore
    trace_conditions:
      # Drop spans from services that never set a name
      - resource.attributes["service.name"] == nil or IsMatch(resource.attributes["service.name"], "^unknown_service")
```

Three notes on that config:

- **It only covers traces.** Metrics and logs need the same lines under `metric_statements` and `log_statements`, and `metric_conditions` and `log_conditions`.
- **Checking for `nil` isn't enough.** A service that never set a name arrives as `unknown_service:java`, not as nothing. That's why the condition also matches the fallback.
- **The syntax is recent.** `trace_conditions` and the `resource.` prefix inside flat statements are the current form. Older Collector releases use nested `traces: span:` and `context: resource` blocks, which are now deprecated.

Dropping telemetry is a blunt tool. Roll it out in staging first, and consider tagging offenders for a week before you start dropping them. A team that loses its traces without warning learns the wrong lesson.

The `filter` processor is the right tool for rejection. Don't reach for `transform`'s `limit()` function here. It caps the *number* of attributes on a record, and it never drops the record itself.

## The checklist

Before you ship a service, check:

- [ ] `service.name` is set, stable across releases, and unique within its namespace
- [ ] `service.version` is the build version (not `latest`, not `unknown`)
- [ ] `service.namespace` groups this service with its neighbours
- [ ] `deployment.environment.name` is exactly `production`, `staging`, or `development`
- [ ] Kubernetes attributes come from the Collector (`k8s_attributes`), and `k8s.cluster.name` has a source
- [ ] Cloud attributes come from the Collector (`resource_detection`) running on the same node
- [ ] Resource attributes are set once at SDK start, not per span

Identity is one half of the vocabulary. The other half is what you call everything inside a span: [OTel Semantic Conventions](/guides/otel-semantic-conventions/) covers the standard names for HTTP, database, messaging, and RPC attributes.

<!-- TODO: Add section on custom resource attributes for business context (team, cost-centre, product) -->
<!-- TODO: Add section on resource attribute cardinality (service.instance.id is high cardinality as a metric label) -->
<!-- TODO: Add worked examples for Python, Go, Java SDK initialisation with resource attributes -->
