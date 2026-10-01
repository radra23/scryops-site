---
title: "eBPF Continuous Profiling: A Practical Guide"
date: 2026-10-01
draft: false
excerpt: "Profile every process on a node with one DaemonSet and no code changes. How eBPF profilers work, which tool to pick, a tested Parca deployment, and the privileges, storage and trace-linking limits you need to plan around."
readtime: 8
tags: ["eBPF", "Profiling", "Kubernetes"]
---

Continuous profiling is where eBPF pays off fastest: one agent per node watches every process on the machine, all the time, and nobody has to touch application code.

This guide covers how that works, which tool to pick, a Parca deployment on Kubernetes (we ran the same server and agent end to end in Docker), and the limits worth knowing before you roll it out. If you're still deciding whether eBPF is ready for your fleet at all, start with [Is eBPF production-ready?](/qa/ebpf-production-ready/) If you're unsure how profiling differs from the tracing you already have, read [profiling vs tracing](/qa/profiling-vs-tracing/).

## How an eBPF profiler works

A sampling profiler asks the CPU "what are you running right now?" many times a second and counts the answers. An eBPF profiler does the asking from inside the kernel:

1. It registers a timer through the kernel's perf events, 19 times a second per CPU by default for Parca Agent.
2. On each tick, a small eBPF program walks the stack of whatever is running on that CPU, whichever process it belongs to.
3. Native frames (C, C++, Rust, Go) are unwound directly. Interpreted and JIT runtimes such as the JVM, .NET, Python, Ruby, PHP and Node.js need runtime-specific unwinders, which the [OpenTelemetry eBPF profiler](https://github.com/open-telemetry/opentelemetry-ebpf-profiler) ships for each of them.
4. The kernel side hands each stack to the agent in user space, which deduplicates and counts them and periodically ships them to a backend that turns them into flame graphs.

That design is where the selling points come from:

- **No application changes.** No SDK, no restart, no redeploy. If a process runs on the node, it gets profiled.
- **Language-agnostic.** One agent covers a Go service, a Python worker and a JVM in the same cluster.
- **Low overhead.** The OpenTelemetry eBPF profiler sets itself 1% CPU and 250 MB of memory as [upper limits in its testing](https://github.com/open-telemetry/opentelemetry-ebpf-profiler) In our test below, Parca Agent profiled every process on a lightly loaded 8-CPU machine using about 0.5% of one core, but 210–260 MiB of memory, right at that ceiling.

## Picking a tool

Parca and Grafana Pyroscope both collect with the OpenTelemetry eBPF profiler now (Parca Agent switched in [v0.32.0](https://github.com/parca-dev/parca-agent/releases/tag/v0.32.0); Alloy's `pyroscope.ebpf` embeds Grafana's fork of it), so stack quality is similar. The difference is what surrounds it.

| | Parca | Grafana Pyroscope | Pixie |
|---|---|---|---|
| What it is | Dedicated open-source continuous profiler | Profiling backend in the Grafana stack | Kubernetes observability toolkit (CNCF Sandbox) |
| eBPF collection | Parca Agent DaemonSet | Grafana Alloy's [`pyroscope.ebpf`](https://grafana.com/docs/alloy/latest/reference/components/pyroscope/pyroscope.ebpf/) component | Built in |
| Also collects from apps | Scrapes `pprof` endpoints | Push from per-language SDKs, or pull `pprof` with Alloy's `pyroscope.scrape` | No |
| Storage | [FrostDB](https://www.parca.dev/docs/storage), in memory by default (object storage with `--enable-persistence`) | Object storage | In-cluster only |
| Pick it when | You want a standalone profiler with the fewest moving parts | You already run Grafana, or you need span-level trace links | You want protocol tracing and metrics in the same tool |

Pixie's CPU profiles cover [compiled languages only](https://docs.px.dev/about-pixie/data-sources/) (Go, Rust, C/C++), so it isn't the right pick if your hot paths run on the JVM or Python.

## Deploying Parca on Kubernetes

Parca publishes a ready-to-apply manifest with every release. Use it rather than writing the DaemonSet by hand: an eBPF agent needs a handful of host mounts and privileges, and missing any one of them fails in ways that aren't obvious.

```bash
# The server: a Deployment and a Service on :7070, in the "parca" namespace
kubectl apply -f https://github.com/parca-dev/parca/releases/download/v0.29.1/kubernetes-manifest.yaml

# The agent: a DaemonSet that ships to parca.parca.svc.cluster.local:7070
kubectl apply -f https://github.com/parca-dev/parca-agent/releases/download/v0.50.0/kubernetes-manifest.yaml
```

Those are the current releases as of October 2026. Pin the versions you've tested, and upgrade server and agent together.

### What the agent manifest actually asks for

Your security team will want to know why a profiler needs this much access. Here are the parts of the official DaemonSet that matter, trimmed:

```yaml
# trimmed: volumes (hostPath) and the remaining mounts omitted
spec:
  template:
    spec:
      hostPID: true                      # see every process on the node
      containers:
      - name: parca-agent
        image: ghcr.io/parca-dev/parca-agent:v0.50.0
        args:
        - --node=$(NODE_NAME)            # label profiles with the node name
        - --remote-store-address=parca.parca.svc.cluster.local:7070
        - --remote-store-insecure        # plaintext gRPC inside the cluster
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        securityContext:
          privileged: true               # load eBPF programs
          capabilities:
            add: [SYS_ADMIN]
        volumeMounts:
        - { name: debugfs, mountPath: /sys/kernel/debug }   # kernel tracepoints
        - { name: bpffs,   mountPath: /sys/fs/bpf }
        - { name: cgroup,  mountPath: /sys/fs/cgroup }      # map PIDs to containers
```

The `debugfs` mount is the one people drop when they "simplify" the manifest. Without it, the agent loads its eBPF program and then exits with `neither debugfs nor tracefs are mounted` while trying to attach to the scheduler's tracepoints. We hit exactly that in testing.

The manifest also creates a ServiceAccount and ClusterRole so the agent can read pod metadata, and a ConfigMap of relabel rules that turns it into namespace, pod and container labels. It labels the `parca` namespace `privileged` for Pod Security admission, so check your cluster policy allows that.

### Check that profiles are arriving

Port-forward the server and ask it what it has:

```bash
kubectl -n parca port-forward svc/parca 7070:7070 &

# Profile types the server has received
curl -s localhost:7070/api/profiles/types
# {"types":[{"name":"parca_agent","sampleType":"samples","sampleUnit":"count",
#            "periodType":"cpu","periodUnit":"nanoseconds","delta":true}]}

# Which processes have been profiled
curl -s localhost:7070/api/profiles/labels/comm/values
```

Within a minute, the `comm` values should list processes you never instrumented: your services, plus node daemons such as the container runtime and kubelet. Then open `http://localhost:7070` for the flame graphs.

We ran this server and agent pair as plain Docker containers on a Linux 6.12 kernel, with the same flags and mounts as the manifests. A busy-loop shell process and an unrelated .NET process both showed up in the profile within the first minute, with no changes to either.

## Reading the flame graph

A flame graph shows where CPU time went across all the samples in your window. The horizontal axis is **not** time. Width is the share of samples that included a frame, and in the [classic layout](https://www.brendangregg.com/flamegraphs.html) frames are sorted alphabetically so identical stacks merge.

Parca and Pyroscope draw the graph root-at-top (strictly an icicle graph): the total is the top bar, and each row below shows what its parent called. Look for:

- **Wide frames with nothing below them.** That function is burning CPU itself rather than through what it calls, which usually makes it the culprit.
- **Unexpected frames.** Garbage collection, serialisation, logging or regex taking a large share of the width.
- **Deep, narrow towers.** Usually harmless, but worth a look if a recursive call shows up somewhere it shouldn't.

Filter by the labels the agent adds (node, namespace, pod, container) to compare one replica against the rest. That's how you find the one pod of twenty that's misbehaving.

## Plan for these before production

- **Storage is in memory by default.** The server keeps profiles in 512 MiB of active memory, and the manifest's data volume is an `emptyDir`. Add `--enable-persistence` and point the bucket config in `parca.yaml` at object storage (S3, GCS and others are supported) if you want history to survive a restart.
- **Budget the agent's memory, not just its CPU.** Our agent sat at 210–260 MiB. Across a large fleet that's the real cost, so set requests and limits once you've measured your own nodes.
- **Expect CPU profiles.** On-CPU sampling is what Parca Agent's eBPF profiler gives you. Memory-allocation and lock-contention profiles need hooks inside the runtime, which is where language SDKs still win.
- **Leave the sampling rate alone at first.** 19 Hz per CPU (`--profiling-cpu-sampling-frequency`) is plenty for continuous use. A prime number avoids sampling in lockstep with periodic work.
- **Don't expect span-level trace links.** An eBPF agent usually can't see which span is active inside your process. The exceptions need the app's cooperation: Parca reads trace IDs that Go programs attach as [goroutine labels](https://github.com/polarsignals/otel-profiling-go), and its experimental [custom labels](https://github.com/parca-dev/parca-agent/releases/tag/v0.33.0) do the same for Rust, C and C++. Grafana's traces-to-profiles feature uses [SDK-based span profiles](https://grafana.com/docs/pyroscope/latest/configure-client/trace-span-profiles/), not eBPF. If linking slow spans to their CPU samples matters most to you, plan on an SDK for those services.
- **Check the kernel first.** Parca Agent needs [5.3+ with BTF](https://github.com/parca-dev/parca-agent) (in practice 5.4+, or a vendor backport), and the profiler it builds on may need 5.10+ in future releases. The [production-readiness Q&A](/qa/ebpf-production-ready/) has the per-tool floors.

CPU profiling with eBPF gives the best signal-to-cost ratio for fleet-wide profiling: no code changes, around 1% CPU or less, and flame graphs that work across languages in the same cluster. Start there. Add SDK-based profiling only for the services where you need memory profiles or span-level trace links.

{{< obs-mascot class="ranger" quip="I sampled every process on this node nineteen times a second. The hottest stack was a logger formatting messages nobody reads." >}}
