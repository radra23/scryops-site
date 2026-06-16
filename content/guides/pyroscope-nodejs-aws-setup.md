---
title: "Grafana Pyroscope on AWS with Node.js: A Setup Reference"
date: 2026-06-16
draft: true
excerpt: "A complete reference for deploying Grafana Pyroscope on AWS and wiring a Node.js service to ship profiles to it. Covers two deployment shapes — single EC2 and ECS Fargate — with S3 storage, TLS termination, and the tagging patterns that make profiles actually useful."
readtime: 12
tags: ["Profiling", "Observability", "Grafana", "Operations"]
---

<!--
GUIDE: In-depth technical reference. This is the "build the thing" document.
The source material is a real project write-up (eu-west-1, domain
pyroscope-cloudops-tooling.ninja, Pyroscope 1.10.0). Write from it faithfully
but reorganise for clarity and apply tech-storyteller voice.

This guide should be self-contained — a reader who has NOT read the article
should be able to follow it. The article is for "should I bother"; this is
for "now I'm doing it."

STRUCTURE:

## What You're Building
Open with the architecture diagram from the source material (adapted as a
Mermaid diagram — the ASCII art in the source is good but should become a
proper {{</* mermaid */>}} shortcode):

Node.js tasks (ECS Fargate) → Pyroscope server (EC2 or ECS) → Grafana

Two deployment shapes:
1. Single EC2 with Docker Compose — dev/prototype, fast to stand up
2. ECS Fargate + ALB + EFS — production-leaning

Both are documented. The guide is structured so readers can stop at Shape 1
and have something working, then continue to Shape 2 for production hardening.

## Prerequisites / Assumptions
- AWS account with permissions to create VPCs, EC2, ECS, EFS, ALB, Route 53,
  ACM, IAM
- Region: pick one and stick with it throughout (the source uses eu-west-1;
  the guide should show the pattern, not hard-code the region)
- Node.js service already running somewhere — this guide wires profiling onto
  an existing service, it doesn't build one from scratch

## Layer 1 — The Network
Reproduce the VPC setup from the source, but frame it as a checklist rather
than a narrative. The CIDR plan the source uses is standard and fine:
- VPC with DNS hostnames AND DNS support both enabled (both required — note
  that DNS support alone isn't sufficient; hostname resolution needs both flags)
- Public subnets (with auto-assign public IP) + Internet Gateway route
- Private subnets + NAT Gateway route

Include the tip about saving VPC resource IDs to an env file early — this
saves significant copy-paste pain in the layers above.

## Layer 2a — EC2 Single-Instance Deployment
Reproduce the Docker Compose config from the source. Keep the three-port
table (4040 HTTP, 9095 gRPC, 7946 memberlist) — this is genuinely useful
reference material and saves time when debugging connectivity.

The minimal Compose config from the source is correct and should be included
verbatim (it's working config from the real project).

Note on `-target=all`: this runs Pyroscope as a monolith (all components in
one process). Fine for dev/single-instance. For production-scale deployments
you'd split components, but that's out of scope here.

## Layer 2b — ECS Fargate Deployment
Reproduce the task definition JSON from the source. Key points to emphasise:
- 1 vCPU / 2 GB is sufficient to start; profile it under load before sizing up
- EFS mount is mandatory for durability — without it, a task restart loses
  all stored profiles
- The ALB health check should target /ready on port 4040 (Pyroscope exposes
  this endpoint)
- Route 53 alias A-record (not CNAME, not IP) pointing at the ALB's hosted-
  zone canonical DNS name — ALBs don't have stable IPs, so the alias target
  uses the canonical hosted-zone ID

## Layer 3 — TLS and the Front Door
Three options from the source, each with a use case:

1. Nginx on the EC2 box — most control; supports bearer-token auth, WebSocket
   upgrade, custom timeouts. The workhorse. Show a minimal nginx.conf snippet.
   
2. ALB — natural fit for ECS. TLS termination and health checks built in.
   ACM certificate (DNS-validated via Route 53 CNAME).

3. API Gateway — viable but has a specific gotcha worth documenting:
   the integration TYPE is "HTTP Proxy" (not "ANY" — that's the METHOD).
   Use a {proxy+} greedy resource with the ANY method and HTTP_PROXY
   integration pointing at the instance's private IP.

## Storage
Two backends:
- filesystem — dead simple, right for local dev and the single-instance shape
- S3 — the production answer

Include the IAM policy from the source (it's correct least-privilege and
worth preserving exactly):
  - s3:ListBucket on the bucket ARN (not bucket/*)
  - s3:GetObject, s3:PutObject, s3:DeleteObject on bucket/*

Include the server config YAML from the source. IMPORTANT: note the two
config gotchas from the war stories (these belong here as well as in the
how-to, because they'll surface during setup):
  - replication_factor must be nested correctly inside the ring kvstore block
  - Retention settings (min_free_disk_gb, etc.) belong directly under
    pyroscopedb, NOT in a nested retention_policy block

## A Note on Memberlist and the Hash Ring
Short section — the source's explanation is good and worth preserving:
- Pyroscope uses a hash ring for sharding/replication
- Memberlist (port 7946) is the only supported KV store for the ring
- Single instance: invisible, nothing to configure
- Multiple replicas: instances discover each other via -memberlist.join
- In Kubernetes (out of scope for this guide but worth flagging): headless
  Service with dnssrv+ discovery

## Wiring the Node.js Service

### Installation
npm install @pyroscope/nodejs

Note the prebuilt binary situation: common platforms (Linux arm64/x64,
Alpine x64, macOS arm64/x64, Windows x64, Node 16/18/20/22/23) ship
prebuilt. Exotic platforms fall back to node-gyp compilation. Node 16+
required.

### Minimal Init
The three-line version from the source is correct and should be the starting
point:
```javascript
const Pyroscope = require('@pyroscope/nodejs');
Pyroscope.init({
  serverAddress: 'http://pyroscope:4040',
  appName: 'myNodeService',
  tags: { region: process.env.REGION || 'default' }
});
Pyroscope.start();
```

### Configuration Reference Table
Reproduce the table from the source. Key defaults to call out explicitly:
- flushIntervalMs defaults to 60,000ms (60 seconds) — NOT "a few seconds."
  The source prose says "every few seconds" but the table correctly shows
  60000. Use the table value. The sampling happens continuously at ~100Hz;
  the FLUSH (shipping to server) is every 60 seconds by default.

### Static vs. Dynamic Tags
This section is one of the more valuable parts of the source. Preserve:
- Static tags: set once in init(), describe the process (region, hostname)
- Dynamic tags: set per code path with wrapWithLabels(), describe what the
  code is doing (endpoint, job type, etc.)

The wrapWithLabels example from the source is minimal but correct. Show
a more realistic example: wrapping an Express route handler so you can
separate /checkout performance from /search performance in the flame graph.

### The ECS Tagging Pattern — CORRECTED
⚠️  FACTUAL CORRECTION REQUIRED: The source code uses process.env.AWS_ECS_TASK_ID,
AWS_ECS_CLUSTER, AWS_ECS_SERVICE_NAME — but these are NOT standard ECS
environment variables. ECS does not inject them automatically.

The task ARN is available via the ECS Container Metadata Service:
  curl ${ECS_CONTAINER_METADATA_URI_V4}/task

This returns JSON including TaskARN, Family, Cluster, etc.

Two correct approaches to document:

Option A: Inject them explicitly in the task definition environment block:
```json
{
  "environment": [
    { "name": "ECS_TASK_FAMILY", "value": "pyroscope-demo" }
  ]
}
```
(Hardcoded in task def — works, but doesn't give you the dynamic task ID)

Option B: Fetch from the metadata endpoint at process startup:
```javascript
async function getECSMetadata() {
  const metadataUri = process.env.ECS_CONTAINER_METADATA_URI_V4;
  if (!metadataUri) return {};
  const resp = await fetch(`${metadataUri}/task`);
  const data = await resp.json();
  return {
    taskId: data.TaskARN?.split('/').pop(),
    cluster: data.Cluster?.split('/').pop(),
    family: data.Family,
  };
}

const ecsMeta = await getECSMetadata();
Pyroscope.init({
  serverAddress: '...',
  appName: 'myNodeService',
  tags: {
    instance: ecsMeta.taskId || os.hostname(),
    cluster:  ecsMeta.cluster  || 'local',
    service:  ecsMeta.family   || 'unknown',
    region:   process.env.AWS_REGION || process.env.REGION,
  }
});
```

The tagging concept from the source is excellent (stamp every profile with
which task produced it, then filter by task when one of twenty is misbehaving).
The implementation just needs the correct env var names.

### Debugging the Client
Preserve: DEBUG=pyroscope node index.js before assuming a network problem.

## Wiring Grafana
Short section: add a Pyroscope data source in Grafana pointing at the fronted
URL, set auth if the server is protected, use the flame graph panel type.
The scrape interval referenced in the source (15s) is the Grafana UI refresh
interval, NOT the SDK flush interval (which is 60s by default) — keep this
distinction clear.

## Verification Checklist
Reproduce the connectivity checklist from the source — it's immediately
useful and well-structured:
- ss -tlnp to verify ports are listening
- curl /ready for HTTP health
- nc -zv for gRPC port
- docker-compose logs

Include the mental checklist (public subnet, security groups, DNS resolution,
data directory permissions, durable AWS credentials).

FORMAT NOTES:
- The architecture diagram should be a {{< mermaid >}} sequenceDiagram or
  flowchart — the ASCII art from the source is good; convert it
- Include the Docker Compose config and task definition JSON verbatim
  (they're working configs from the real project)
- Each "layer" section should note which of the war-stories applies to it,
  with a link to the how-to: "See [Five Things That Will Break Your Pyroscope
  Deployment] for the specific failure modes in this layer."
- The CORRECTED ECS tagging section is important — make it visually distinct
  (insight box or clear callout)

CROSS-LINK TO:
- Article: content/articles/continuous-profiling-the-missing-signal.md
  (for readers who want the "why" before the "how")
- How-to: content/howtos/pyroscope-deployment-war-stories.md
  (for the failure modes at each layer — link from relevant sections)
-->
