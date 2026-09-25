---
title: "Scraping Prometheus Metrics Through Istio mTLS"
date: 2026-06-15
draft: true
excerpt: "Enabling mTLS in Istio secures every service call in your cluster — and also breaks Prometheus's plain HTTP scraper. Three patterns for bridging the gap: in-mesh Prometheus with certificate sharing, metrics merging at port 15020, and per-port mTLS exemption."
readtime: 10
tags: ["Prometheus", "Kubernetes", "Service Mesh", "Observability", "Metrics", "Security"]
---

> "Security without observability is blindness with a lock on the door."
> — Anonymous

When you enable mTLS in Istio, every service-to-service call in your cluster becomes encrypted and mutually authenticated — without changing a line of application code. It's one of the best arguments for adopting a service mesh. Then you try to scrape Prometheus metrics and discover the lock works on everyone, including your monitoring infrastructure.

The metrics endpoint is live. Prometheus can reach the IP. But the Envoy sidecar in front of every pod has no reason to trust an unauthenticated HTTP connection, and so it closes it. Your dashboards go dark.

This isn't a bug. It's exactly the behaviour you configured. The question is how to make Prometheus a legitimate participant in a secure mesh — without compromising the security you just gained.

## Why the Sidecar Locks the Door

In STRICT mTLS mode, the Envoy sidecar intercepts all inbound traffic to a pod and requires a valid client certificate before forwarding anything. A plain HTTP scrape from Prometheus carries no certificate. From the sidecar's perspective, this is an anonymous connection from an untrusted source, and it's rejected accordingly.

Even in PERMISSIVE mode — which accepts both mTLS and plaintext — ALPN negotiation between Envoy and older Prometheus versions can behave inconsistently, depending on your Istio and Envoy build. PERMISSIVE mode is not a reliable workaround; it's a migration tool, not an observability strategy.

The core issue: Prometheus was designed to scrape plain HTTP. Istio was designed to encrypt and authenticate everything. You need to bridge that gap deliberately.

{{< mermaid >}}
sequenceDiagram
    participant P as Prometheus
    participant S as Envoy Sidecar
    participant A as App (metrics port)
    Note over P,S: STRICT mTLS active
    P->>S: HTTP GET /metrics (no cert)
    S-->>P: Connection closed — not authenticated
    Note over A: Metrics unreachable
{{< /mermaid >}}

## Three Paths Through the Door

The solutions all work. They differ in how much security posture you trade for operational simplicity.

---

### Path 1: Join the Mesh — In-mesh Prometheus

The cleanest solution is to make Prometheus a first-class mesh citizen. Inject an Envoy sidecar into the Prometheus pod, then use Istio's `OUTPUT_CERTS` mechanism to export the mTLS certificates to a shared memory volume. Prometheus reads those certificates and presents them when making scrape requests. Your workloads receive an authenticated mTLS connection — indistinguishable from any other service-to-service call.

The `OUTPUT_CERTS` proxy metadata directive tells the sidecar to write the workload certificate, key, and root CA to a specified path. A shared `emptyDir` volume bridges the gap between the sidecar container (which writes the certs) and the Prometheus container (which reads them).

```yaml
# Prometheus Deployment — spec.template section (illustrative excerpt)
metadata:
  annotations:
    sidecar.istio.io/inject: "true"
    # Disable traffic interception — Prometheus presents certs directly,
    # bypassing the sidecar for its own outbound scrape connections
    traffic.sidecar.istio.io/includeInboundPorts: ""
    traffic.sidecar.istio.io/includeOutboundIPRanges: ""
    # Write mTLS certs to a shared volume
    proxy.istio.io/config: |
      proxyMetadata:
        OUTPUT_CERTS: /etc/istio-output-certs
    sidecar.istio.io/userVolumeMount: '[{"name":"istio-certs","mountPath":"/etc/istio-output-certs"}]'
spec:
  serviceAccountName: prometheus
  containers:
  - name: prometheus-server
    volumeMounts:
    - name: istio-certs
      mountPath: /etc/prom-certs/
  volumes:
  - name: istio-certs
    emptyDir:
      medium: Memory   # Keeps key material out of disk
```

With the certificates on disk, tell each Prometheus scrape job to use them:

```yaml
# prometheus.yml — scrape job tls_config
scrape_configs:
- job_name: 'istio-mesh'
  scheme: https
  tls_config:
    ca_file: /etc/prom-certs/root-cert.pem
    cert_file: /etc/prom-certs/cert-chain.pem
    key_file: /etc/prom-certs/key.pem
  kubernetes_sd_configs:
  - role: pod
```

There's one more step. If you're running STRICT mTLS throughout, the Prometheus service account's SPIFFE identity needs to be explicitly authorized to reach metrics ports. Without an `AuthorizationPolicy` on each workload, even a valid mTLS connection returns a 403:

```yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-prometheus-scrape
  namespace: production
spec:
  selector:
    matchLabels:
      app: my-app
  action: ALLOW
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/monitoring/sa/prometheus"]
    to:
    - operation:
        ports: ["9090"]
```

The principal format (`cluster.local/ns/<namespace>/sa/<serviceaccount>`) is the SPIFFE URI Istio uses for workload identity. Adjust namespace and service account name to match your deployment.

**When to choose this:** production environments with strict compliance requirements where any cleartext endpoint — even on an internal port — isn't acceptable. This is the most operationally complex option, but it preserves your mTLS policy from end to end and leaves no plaintext window.

---

### Path 2: Let the Mesh Carry Them — Metrics Merging

Istio's sidecars are already scraping your application's metrics endpoint from inside the pod network. The `enablePrometheusMerge` flag tells them to aggregate those metrics — alongside their own Envoy metrics — and expose the combined output on port 15020, which is deliberately exempted from mTLS.

This is the lowest-friction option for most teams. No cert management. No sidecar injection into Prometheus. No AuthorizationPolicies for scraping.

Enable merging globally in your mesh config:

```yaml
# IstioOperator or MeshConfig
meshConfig:
  enablePrometheusMerge: true
```

Then annotate pods so Prometheus's service discovery finds the merged endpoint:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "15020"
  prometheus.io/path: "/stats/prometheus"
```

Port 15020 is Istio's pilot-agent port. The Envoy sidecar scrapes your application's metrics internally and serves the combined output at `15020/stats/prometheus` over plain HTTP. One scrape, all metrics.

The trade-off is real: you're creating a plaintext window in a mesh that otherwise requires encryption. For most threat models this is acceptable — port 15020 carries no write surface, is not reachable from outside the cluster, and should be restricted to your Prometheus pods via NetworkPolicy. For regulated environments where any cleartext endpoint fails an audit, this approach isn't appropriate.

**When to choose this:** the right default for most teams. Low operational overhead, no changes to Prometheus, works with Prometheus Operator `ServiceMonitor` resources without modification. Ship in an afternoon, not a week.

---

### Path 3: Open a Window — Per-port mTLS Exemption

If you need Prometheus to scrape your application's metrics port directly — not via port 15020 — and you'd rather not run Prometheus inside the mesh, you can disable mTLS selectively for the metrics port using a `PeerAuthentication` resource.

```yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: metrics-cleartext
  namespace: production
spec:
  selector:
    matchLabels:
      app: my-app
  mtls:
    mode: STRICT        # All other ports remain encrypted
  portLevelMtls:
    9090:               # Metrics port only
      mode: DISABLE
```

Every port except 9090 stays under STRICT mTLS. Prometheus scrapes port 9090 over plain HTTP with no certificate configuration needed.

{{< insight >}}
**NetworkPolicy is not optional here.** Disabling mTLS on a port removes the authentication layer for that port entirely — any pod in the cluster can connect to it. Pair every `portLevelMtls: DISABLE` with a NetworkPolicy that restricts inbound access on that port to your Prometheus pod's labels or namespace.
{{< /insight >}}

**When to choose this:** simple deployments where metrics merging doesn't cover your use case (for example, you need to distinguish application metrics from Envoy metrics in separate scrape jobs, or your application uses a metrics format other than Prometheus text exposition). Keep the NetworkPolicy tight.

---

## Beyond the Three Paths

### Custom Metric Labels — The Telemetry API

If you need Istio's generated metrics to carry additional context — for example, tagging request counts by a custom header value — the Telemetry API is the right tool. Available via the stable `telemetry.istio.io/v1` API since Istio 1.20, it lets you add label overrides to mesh-generated metrics without modifying application code:

```yaml
apiVersion: telemetry.istio.io/v1
kind: Telemetry
metadata:
  name: prometheus-custom-dimensions
  namespace: production
spec:
  metrics:
  - providers:
    - name: prometheus
    overrides:
    - match:
        metric: REQUEST_COUNT
      tagOverrides:
        environment:
          value: "request.headers['x-environment']"
```

Tag override values are CEL expressions. `request.headers['x-environment']` reads the header value from each request and attaches it as a label to `istio_requests_total` — propagating business context into mesh metrics without touching your services.

### OTel Collector as Intermediary

If your organization runs an OpenTelemetry Collector pipeline, it can absorb the mTLS problem in one place. Deploy Collectors with sidecar injection (using the same `OUTPUT_CERTS` pattern as Path 1), configure the `prometheus` receiver to scrape workload metrics from inside the mesh using the shared certificates, then forward to your metrics backend via `prometheusremotewrite` or OTLP.

The advantage: certificate management and service account authorization live in one Collector deployment, not spread across every Prometheus scrape job.

### Prometheus Federation

For large clusters or multi-team environments, hierarchical federation often makes the mTLS problem easier to manage. Namespace-scoped Prometheus instances handle fine-grained scraping within their own security boundary; a global instance federates summary metrics upward for cross-cluster dashboards. Each local instance only needs to solve the mTLS problem for its own namespace, which limits the blast radius of any configuration mistake.

### Ambient Mode — The Sidecar Disappears

Istio's Ambient mode removes per-pod Envoy sidecars entirely, replacing them with a node-level `ztunnel` that handles L4 mTLS transparently. Without a sidecar intercepting each pod's incoming connections, the metrics scraping problem changes significantly: there's no sidecar to negotiate mTLS with Prometheus, and application metrics are accessible directly on their native ports with mesh-level security enforced at a different layer.

Ambient mode eliminates substantial resource overhead from sidecar injection and simplifies the metrics collection story considerably. If you're evaluating Istio for a new cluster, it's worth understanding before committing to the sidecar model.

---

## Choosing Your Path

| Situation | Recommended approach |
|-----------|---------------------|
| Default production deployment | Metrics merging (port 15020) |
| Strict compliance (PCI DSS, HIPAA) | In-mesh Prometheus with STRICT mTLS end-to-end |
| Simple workload, need direct scrape | Per-port mTLS exemption + NetworkPolicy |
| Existing OTel Collector pipeline | OTel Collector with `prometheus` receiver |
| New cluster, evaluating service mesh | Consider Ambient mode before committing to sidecars |
| Need custom label dimensions on mesh metrics | Telemetry API on top of any of the above |

The metrics merging path is the right default because it's the one you can ship without redesigning your certificate infrastructure or redeploying Prometheus. Save the in-mesh approach for environments where your compliance requirements make the complexity worth carrying — that's what it's there for.

---

## See Also

- [Service Mesh Observability](/guides/service-mesh-observability/) — what Istio gives you for free at the infrastructure layer, and what it doesn't
- [How to Enable Distributed Tracing with Istio and OpenTelemetry](/howtos/set-up-istio-distributed-tracing/) — the tracing side of Istio observability
- [OTel Collector Configuration](/guides/otel-exporter-configuration/) — configuring the Collector as a metrics intermediary
