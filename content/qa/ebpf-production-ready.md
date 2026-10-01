---
title: "Is eBPF production-ready for observability use cases?"
date: 2026-10-01
draft: false
answer: "For profiling and network observability on a modern Linux kernel, yes. Cilium, Parca, Pixie and Tetragon all run in production. The caveats are kernel version and BTF support, the privileges the agent needs, and application-level tracing, which still trails what an SDK gives you."
excerpt: "For profiling and network observability on a modern Linux kernel, yes. Cilium, Parca, Pixie and Tetragon all run in production. The caveats are kernel version and BTF support, the privileges the agent needs, and application-level tracing, which still trails what an SDK gives you."
readtime: 3
tags: ["eBPF", "Kubernetes", "Profiling"]
---

Yes for profiling and networking. Clear two gates first, and know where app tracing stands.

## Tools already running in production

- **Cilium** for networking and network observability. It's the data plane behind [GKE Dataplane V2](https://cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2) and [Azure CNI Powered by Cilium](https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium).
- **Parca** and **Grafana Pyroscope** for continuous profiling. Both now collect with the [OpenTelemetry eBPF profiler](https://github.com/open-telemetry/opentelemetry-ebpf-profiler) (Pyroscope through Grafana's fork of it), which sets itself 1% CPU and 250 MB of memory as upper limits in its own testing.
- **Pixie** for Kubernetes observability without code changes: protocol-level request data (HTTP, gRPC, SQL, Kafka and more), resource metrics and CPU profiles, all kept in-cluster. It's a [CNCF Sandbox project](https://www.cncf.io/projects/pixie/), originally from New Relic.
- **Tetragon** for [security observability and runtime enforcement](https://tetragon.io/docs/overview/): process, file and network events, filtered in the kernel.

## What to check before you deploy

{{< mermaid caption="Fig. — Kernel BTF support and agent privileges are the two gates that decide whether eBPF deploys cleanly. Clear them and profiling or networking are safe starting points; app tracing still lags behind what an SDK captures." >}}
flowchart TD
    start["Deploy eBPF for observability?"]
    kernel{"Kernel meets the tool's floor<br/>(5.10+ is safe), BTF enabled?"}
    caps{"Platform lets the agent run<br/>privileged with host PID?"}
    usecase{"Use case?"}
    upgrade["Upgrade the kernel or node image<br/>before rolling out"]
    policy["Allow it for this DaemonSet,<br/>or use a node pool that can"]
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

### Kernel 5.4+ with BTF covers most tools, so audit your fleet first

Modern eBPF tools are built once and run on many kernels thanks to CO-RE ("compile once, run everywhere"). CO-RE reads the kernel's type information (BTF) from `/sys/kernel/btf/vmlinux`, which [arrived in kernel 5.4](https://github.com/iovisor/bcc/blob/master/docs/kernel-versions.md) and only exists when the kernel is built with `CONFIG_DEBUG_INFO_BTF=y`. Current mainstream distributions ship it, and some enterprise kernels backport it to older versions.

Floors vary by tool, so check the one you're deploying:

| Tool | Documented minimum |
|---|---|
| Parca Agent | [5.3+ with BTF](https://github.com/parca-dev/parca-agent) (in practice 5.4+, or a vendor backport) |
| Pixie | [4.14+](https://docs.px.dev/installing-pixie/requirements/) |
| Tetragon | [4.19+ with BTF](https://tetragon.io/docs/installation/faq/) |
| Cilium | [5.10+](https://docs.cilium.io/en/stable/operations/system_requirements/) (or a vendor kernel with the backports) |

The OpenTelemetry eBPF profiler that Parca and Pyroscope now build on [warns](https://github.com/open-telemetry/opentelemetry-ebpf-profiler#supported-linux-kernel-version) that newer releases may need 5.10+. If you're choosing a node image today, 5.10 or newer is the future-proof pick.

### The agent needs more privilege than a normal pod

eBPF programs run in the kernel, not in the container. Loading them takes privileges ordinary workloads never get:

- Profiling agents usually run as a privileged DaemonSet with the host PID namespace. That's how the [official Parca Agent manifest](https://github.com/parca-dev/parca-agent/releases) deploys, with `CAP_SYS_ADMIN` added.
- Kernel 5.8 split `CAP_BPF` and `CAP_PERFMON` out of `CAP_SYS_ADMIN`, so a non-privileged setup is possible, but the real list is longer than those two. Grafana Alloy's [eBPF profiler](https://grafana.com/docs/alloy/latest/reference/components/pyroscope/pyroscope.ebpf/) documents seven: `BPF`, `PERFMON`, `SYS_PTRACE`, `SYS_RESOURCE`, `DAC_READ_SEARCH`, `SYSLOG` and `CHECKPOINT_RESTORE` (`SYS_ADMIN` on kernels older than 5.9), plus root and host PID.
- The official Parca manifest labels its namespace `privileged` for Pod Security admission. Your cluster policy, AppArmor or SELinux rules, or a managed Kubernetes mode may not allow that. Find out before you roll out, not during.

### Application-level tracing lags behind profiling and networking

- **CPU profiling**: mature and low overhead. The OpenTelemetry eBPF profiler covers native code plus the JVM, .NET, Python, Ruby, PHP and Node.js (Pixie profiles compiled languages only).
- **Network observability**: mature. Cilium is the proof.
- **Application-level tracing**: still evolving. eBPF can see common protocols on the wire (HTTP, gRPC, SQL), but not your business context: which customer, which feature flag, which retry. An SDK, or OpenTelemetry auto-instrumentation inside the process, still captures more.

## Bottom line

Start with profiling. It gives the most signal for the least change: no code, no restarts, one DaemonSet. If you want to try it, the [eBPF continuous profiling guide](/guides/ebpf-continuous-profiling/) walks through a Parca deployment.
