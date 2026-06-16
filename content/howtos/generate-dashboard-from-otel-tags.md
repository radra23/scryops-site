---
title: "Generate a Grafana Dashboard from OpenTelemetry Attributes"
date: 2026-06-16
draft: true
excerpt: "A step-by-step walkthrough for building a tag-driven dashboard generator: read OTel resource attributes from your Collector, match them against a convention map, and provision a Grafana dashboard automatically. No ML required."
readtime: 8
tags: ["OpenTelemetry", "Grafana", "Observability", "How-to", "Collector"]
---

<!--
HOW-TO: Step-by-step implementation walkthrough. The reader has come from
either the article (convinced of the concept) or the guide (knows the
attribute→panel mapping). Now they want to build it. This walkthrough should
be concrete, working, and opinionated — pick a specific stack and make it run.

CHOSEN STACK (to keep it concrete):
- OTel Collector (for attribute extraction)
- Prometheus (as the metrics backend, because it's the most common OSS choice)
- Grafana (for dashboard provisioning via the HTTP API / provisioned YAML)
- Python script for the generator (simple, readable)

If the author prefers a different stack (e.g., Grafana Alloy, or targeting
a different backend), adjust accordingly. The important thing is that the
implementation is real and runnable, not pseudocode.

STEPS TO WRITE:

## Prerequisites
- OTel Collector running and scraping services
- Prometheus receiving metrics from the Collector
- Grafana with API access enabled (API key or service account token)
- Python 3.10+ for the generator script

## Step 1: Extract Resource Attributes from the Collector
The generator needs to know what attributes your services emit. Two options:

Option A: Query Prometheus for label values
```
# Get all distinct service.name values
label_values(up, service_name)

# Get all distinct db.system values across services
label_values({db_system!=""}, db_system)
```

Option B: Use the OTel Collector's zpages extension or the debug exporter
to inspect what resource attributes are arriving. Show how to enable zpages
and read the ServiceZ page.

The generator should build a dict: {service_name: {detected_attributes: [...]}}

## Step 2: The Attribute → Template Mapping
Show a clean Python dict (NOT the over-engineered ML version from the PRD):

```python
# The complete mapping — a lookup table, not a model
ATTRIBUTE_TEMPLATES = {
    "db.system": {
        "postgresql": "templates/database-sql.json",
        "mysql":      "templates/database-sql.json",
        "redis":      "templates/database-redis.json",
        "mongodb":    "templates/database-mongo.json",
        "*":          "templates/database-generic.json",  # fallback
    },
    "http.route": "templates/http-service.json",
    "messaging.system": {
        "kafka":      "templates/messaging-kafka.json",
        "rabbitmq":   "templates/messaging-amqp.json",
        "*":          "templates/messaging-generic.json",
    },
    "k8s.deployment.name": "templates/kubernetes-deployment.json",
    "rpc.system": {
        "grpc":       "templates/rpc-grpc.json",
        "*":          "templates/rpc-generic.json",
    },
}
```

Explain: this is the whole intelligence layer. No GNNs, no transformers.
The OTel spec already did the hard work of defining a stable vocabulary.

## Step 3: Parameterize a Grafana Dashboard Template
Show a minimal Grafana dashboard JSON template with variable substitution:
- $SERVICE_NAME → substituted with the actual service.name value
- $DATASOURCE → the Prometheus data source UID
- Panels pre-wired to the right PromQL queries

Show one complete worked example: the http-service.json template with:
- Request rate panel: `rate(http_server_request_duration_seconds_count{service_name="$SERVICE_NAME"}[5m])`
- Error rate panel: same metric filtered to `http_response_status_code=~"5.."`
- p99 latency panel: `histogram_quantile(0.99, rate(http_server_request_duration_seconds_bucket{service_name="$SERVICE_NAME"}[5m]))`

Note: OTel SDK metric naming uses underscores and follows semantic conventions
(http.server.request.duration is the OTel metric name; Prometheus scraping
converts dots to underscores). The queries should use the Prometheus-normalised
names.

## Step 4: Generate and Provision the Dashboard
Show the generator script:

```python
import json
import requests
from pathlib import Path

GRAFANA_URL = "http://localhost:3000"
GRAFANA_TOKEN = "..."  # service account token with Editor role

def load_template(template_path, variables):
    template = Path(template_path).read_text()
    for key, value in variables.items():
        template = template.replace(f"${key}", value)
    return json.loads(template)

def provision_dashboard(dashboard_json, folder_uid=None):
    payload = {
        "dashboard": dashboard_json,
        "overwrite": True,  # idempotent — safe to re-run
        "folderUid": folder_uid,
    }
    resp = requests.post(
        f"{GRAFANA_URL}/api/dashboards/db",
        json=payload,
        headers={"Authorization": f"Bearer {GRAFANA_TOKEN}"},
    )
    resp.raise_for_status()
    return resp.json()["url"]

def generate_dashboards(service_attributes):
    for service_name, attrs in service_attributes.items():
        for attr_name, attr_value in attrs.items():
            template_path = resolve_template(attr_name, attr_value)
            if not template_path:
                continue
            dashboard = load_template(template_path, {
                "SERVICE_NAME": service_name,
                "DATASOURCE": "prometheus",
            })
            url = provision_dashboard(dashboard)
            print(f"Provisioned: {service_name} → {url}")
```

Key point: `overwrite: True` makes this idempotent. Run it on every deploy,
every config change, or on a cron — it won't duplicate dashboards.

## Step 5: Wire It Into Your Deploy Pipeline
Option A: Run the generator as a post-deploy hook. After `kubectl apply`, 
the generator re-scans service attributes and re-provisions any dashboards
that need updating.

Option B: Run it as an OTel Collector processor. The Collector sees every
span and can detect new resource attributes. On first sight of a new
service.name, trigger dashboard provisioning.

Show a minimal CI step (GitHub Actions) that runs the generator on deploy.

## What This Doesn't Handle (And That's Fine)
Be explicit about the limits:
- Custom business metrics (revenue, conversion rate) — these require human
  authorship because no semantic convention describes them
- Cross-service correlation views — a dashboard that spans multiple services
  needs human judgment about which services belong together
- Executive-level aggregations — mapping technical metrics to business outcomes
  is a semantic problem that conventions don't solve

The 80/20: automated generation from conventions gives you the operational
baseline for every service. The dashboards you author by hand are the ones
that answer questions conventions can't anticipate.

## Troubleshooting
Common problems:
- Dashboard overwrites lose manual edits: use Grafana's dashboard versioning,
  or store manual additions in a separate dashboard linked from the generated one
- Prometheus label names differ from OTel attribute names (dots → underscores):
  include a normalisation step in the template variables
- New services don't get dashboards until the generator runs: add the post-deploy
  hook, or run the generator on a 5-minute cron as a fallback

FORMAT NOTES:
- Every code block should be complete and runnable, not pseudocode
- Include a real PromQL query for at least one panel type — show the actual
  OTel metric name (http.server.request.duration) vs Prometheus normalised name
- The Mermaid diagram here should show the pipeline: Collector → attribute
  extraction → template lookup → Grafana API → provisioned dashboard
- One insight box: the idempotency point (overwrite: true) is important enough
  to call out — people worry about running generators repeatedly

CROSS-LINK TO:
- Article: content/articles/tag-driven-dashboards-why-yours-are-already-wrong.md
- Guide: content/guides/otel-semantic-conventions-dashboard-mapping.md
  (for the full attribute → panel reference used in Step 2)
-->
