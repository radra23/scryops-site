---
title: "Getting Started with Grafana Alloy"
date: 2026-03-12
draft: false
excerpt: "Alloy replaces the Grafana Agent. What changed, what stayed the same, and a minimal config to get your first pipeline flowing in under 15 minutes."
readtime: 4
tags: ["Grafana", "OpenTelemetry", "Metrics", "Logs"]
---

Grafana Alloy is the successor to Grafana Agent. It's a vendor-neutral collector built on the same foundations but with a new configuration language and a component-based architecture.

## What changed from Grafana Agent

- **River configuration** replaced YAML. It's a declarative, HCL-like language with explicit data flow between components.
- **Component model** — everything is a component (sources, processors, exporters) wired together explicitly.
- **Built-in UI** — Alloy ships with a web UI for inspecting component health and data flow.

## Quick start

### Install

```bash
# macOS
brew install grafana/grafana/alloy

# Docker
docker run -v ./config.alloy:/etc/alloy/config.alloy \
  grafana/alloy:latest run /etc/alloy/config.alloy
```

### Minimal config

```hcl
// config.alloy — scrape Prometheus metrics and ship to Mimir

prometheus.scrape "default" {
  targets = [
    {"__address__" = "localhost:9090"},
  ]
  forward_to = [prometheus.remote_write.mimir.receiver]
}

prometheus.remote_write "mimir" {
  endpoint {
    url = "http://mimir:9009/api/v1/push"
  }
}
```

### Adding logs

```hcl
local.file_match "varlog" {
  path_targets = [{"__path__" = "/var/log/*.log"}]
}

loki.source.file "logs" {
  targets    = local.file_match.varlog.targets
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
  }
}
```

## What stayed the same

- Still supports Prometheus scraping, Loki log collection, and OTel trace forwarding.
- Still runs as a single binary with minimal resource footprint.
- Still integrates tightly with the Grafana ecosystem.

## When to migrate

If you're on Grafana Agent static mode, plan the migration now — Alloy is the actively developed path forward. The River config takes some getting used to, but the explicit data flow makes complex pipelines much easier to reason about.
