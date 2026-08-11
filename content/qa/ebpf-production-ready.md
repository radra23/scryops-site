---
title: "Is eBPF production-ready for observability use cases?"
date: 2026-03-22
draft: true
answer: "For most Linux workloads on kernel 5.8+, yes. eBPF-based tools like Cilium, Pixie, and Parca are running in production at scale. The main caveat is kernel version requirements and container runtime compatibility."
excerpt: "For most Linux workloads on kernel 5.8+, yes. eBPF-based tools like Cilium, Pixie, and Parca are running in production at scale. The main caveat is kernel version requirements and container runtime compatibility."
readtime: 3
tags: ["eBPF", "Kubernetes", "Profiling"]
---

Yes — with caveats.

## Four tools running at scale today

- **Cilium** for networking and network observability — used by major cloud providers.
- **Parca / Pyroscope** for continuous profiling — low overhead, proven at scale.
- **Pixie** for auto-instrumented Kubernetes observability — traces, metrics, and profiles without code changes.
- **Tetragon** for security observability — runtime enforcement and audit logging.

## Three things to check before you deploy

{{< mermaid caption="Fig. — Kernel BTF support and capability grants are the two gates that decide whether eBPF deploys cleanly. Clear them and profiling or networking are safe starting points; app tracing still lags behind what an SDK captures." >}}
flowchart TD
    start["Deploy eBPF for observability?"]
    kernel{"Linux kernel ≥ 5.8<br/>BTF support?"}
    caps{"Container runtime<br/>grants CAP_BPF?"}
    usecase{"Use case?"}
    upgrade["Upgrade kernel first<br/>or use reduced-feature mode"]
    policy["Adjust AppArmor / SELinux<br/>or use managed node image"]
    profiling["CPU profiling<br/>Mature — start here"]
    network["Network observability<br/>Mature — Cilium proven at scale"]
    tracing["App-level auto-tracing<br/>Evolving — SDK gives more context"]
    start --> kernel
    kernel -->|No| upgrade
    kernel -->|Yes| caps
    caps -->|No| policy
    caps -->|Yes| usecase
    usecase -->|profiling| profiling
    usecase -->|network| network
    usecase -->|app tracing| tracing
    style profiling fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style network fill:#1C2A1C,stroke:#1C7A2E,color:#28CA41,stroke-width:1.5px
    style tracing fill:#2A1A0A,stroke:#D4820A,color:#F5A623,stroke-width:2.5px,stroke-dasharray:5 3
    style upgrade fill:#2A0A0A,stroke:#CC4444,color:#FF6060,stroke-width:3px
    style policy fill:#2A1A0A,stroke:#D4820A,color:#F5A623,stroke-width:2.5px,stroke-dasharray:5 3
{{< /mermaid >}}

### BTF requires kernel 5.8+ — audit your fleet first

Most eBPF observability tools require Linux kernel 5.8+ for BTF (BPF Type Format) support. Older kernels may work but with reduced functionality and more manual setup.

### Your container runtime needs explicit capability grants

eBPF programs run in the kernel, not in the container. This means:

- Your container runtime must allow the necessary capabilities (`CAP_BPF`, `CAP_PERFMON`).
- On managed Kubernetes (EKS, GKE, AKS), check if the node kernel supports BTF.
- Some security policies (AppArmor, SELinux) may need adjustments.

### Application-level tracing lags behind CPU profiling and networking

- **CPU profiling**: very mature, low overhead.
- **Network observability**: mature (Cilium is proof).
- **Application-level tracing**: still evolving — auto-instrumentation via eBPF works for common protocols (HTTP, gRPC, SQL) but won't capture application-specific context like a proper SDK would.

## Bottom line

Start with profiling — it delivers the highest signal with the least kernel-capability exposure.
