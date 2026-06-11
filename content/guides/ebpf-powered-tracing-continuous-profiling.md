---
title: "eBPF-Powered Tracing: A Practical Guide to Continuous Profiling"
date: 2026-03-22
draft: true
excerpt: "From kernel hooks to flame graphs — instrument your infrastructure without touching application code, and why that matters for high-throughput systems."
readtime: 12
tags: ["eBPF", "Profiling", "Tracing", "Kubernetes"]
---

eBPF has moved from kernel-hacker curiosity to mainstream observability tool. Continuous profiling — always-on, low-overhead CPU and memory profiling — is the killer use case.

## Zero-change instrumentation is eBPF's core advantage

Traditional profilers require code changes or runtime agents. eBPF hooks into the kernel directly, which means:

- **Zero application changes** — no SDK, no library, no restart.
- **Low overhead** — typically under 1% CPU impact.
- **Language-agnostic** — works with Go, Rust, Java, Python, C++ — anything that runs on Linux.

## Parca, Pyroscope, and Pixie: the production choices today

### Parca
Open-source continuous profiling with eBPF-based collection. Stores profiles in a custom columnar format and provides a UI for flame graph analysis.

### Pyroscope (Grafana)
Now part of the Grafana stack. Supports both push-based and eBPF-based collection. Integrates with Grafana dashboards for correlating profiles with traces and metrics.

### Pixie (New Relic)
Auto-instruments Kubernetes workloads using eBPF. Captures traces, metrics, and profiles without any code changes. Data stays in-cluster by default.

## Getting started: Parca DaemonSet, no code changes

### Prerequisites
- Linux kernel 5.8+ (for BTF support)
- `CAP_BPF` and `CAP_PERFMON` capabilities
- For Kubernetes: privileged containers or appropriate security contexts

### Minimal Parca setup

```yaml
# parca-agent DaemonSet (simplified)
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: parca-agent
spec:
  selector:
    matchLabels:
      app: parca-agent
  template:
    spec:
      hostPID: true
      containers:
      - name: parca-agent
        image: ghcr.io/parca-dev/parca-agent:v0.31.0  # pin a version — :latest disables Kubernetes image deduplication
        securityContext:
          privileged: true
        args:
        - --store-address=parca-server:7070
        - --node=$(NODE_NAME)
```

## Interpreting flame graphs

A flame graph shows you where your CPU time is actually going. The x-axis is **not** time — it represents the sampled population, sorted alphabetically by function name to merge identical stacks. Width is the proportion of samples that included that frame; left-to-right position is meaningless.

Look for:
- **Wide frames** — functions consuming disproportionate CPU.
- **Deep stacks** — excessive recursion or abstraction layers.
- **Unexpected frames** — garbage collection, serialization, or framework overhead you didn't expect.

## Start with CPU profiling; memory profiling adds overhead

- Start with **CPU profiling only**. Memory profiling adds more overhead.
- Set a reasonable **sampling rate** (19Hz or 49Hz are common defaults).
- Use **labels** to filter profiles by service, pod, or node.
- **Storage costs** add up — configure retention policies early.

CPU profiling with eBPF gives you the highest signal-to-cost ratio of any profiling approach: no code changes, under 1% overhead, and flame graphs that work across languages in the same cluster. Start there. Add memory profiling and network profiling only after you have a question those signals can answer that CPU profiling cannot.

{{< obs-mascot class="ranger" quip="I tracked the latency across fourteen services and three time zones. It was DNS. It is always DNS." >}}
