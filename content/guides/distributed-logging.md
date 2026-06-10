---
title: "Distributed Logging"
date: 2026-06-07
draft: true
excerpt: "How logs flow across service boundaries in a distributed system — collection, aggregation, correlation, and the patterns that make it work at scale."
readtime: 8
tags: ["Logs", "Observability", "OpenTelemetry"]
---

# Distributed Logging

Single-service logging is a solved problem. Distributed logging is not. When a request touches ten services, each service writes its own log stream to its own destination, and those streams share nothing but a timestamp you can't fully trust. Correlating a failure across that span requires trace IDs threaded through every log line, a central aggregation layer, and a consistent schema. Without those, you're reading ten separate stories and guessing at the plot.

## Core Concepts

### 1. Distributed Logging Components

A production-grade logging pipeline has five distinct responsibilities:

- **Log Collection**: Agents or sidecars pulling log streams from each service
- **Log Aggregation**: A central layer that ingests, normalizes, and indexes log events
- **Log Storage**: Durable, queryable storage with defined retention and rotation policies
- **Log Analysis**: Query and correlation tooling for surfacing patterns across services
- **Log Visualization**: Dashboards and search UIs that make cross-service state legible to operators

### 2. Log Types

Different log categories serve different operational purposes:

- **Application Logs**: Runtime behavior — what the application executed and what it returned
- **System Logs**: Infrastructure-level events — kernel, systemd, container runtime
- **Access Logs**: Inbound request records — method, path, status, latency
- **Audit Logs**: State-change records for compliance and accountability
- **Security Logs**: Authentication attempts, authorization failures, anomalous access patterns

## Implementation Patterns

### 1. Log Collection

Each log event must carry trace context from the moment it's emitted. Without `trace_id` and `span_id`, log-to-trace correlation is impossible downstream.

```python
from opentelemetry import trace
import logging
import json
import time

class DistributedLogger:
    def __init__(self, service_name):
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        
    def log(self, level, message, **kwargs):
        current_span = trace.get_current_span()
        context = current_span.get_span_context()
        
        log_entry = {
            'timestamp': time.time(),
            'level': level,
            'message': message,
            'service': self.service_name,
            'trace_id': format(context.trace_id, '032x'),
            'span_id': format(context.span_id, '016x'),
            **kwargs
        }
        
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(numeric_level, json.dumps(log_entry))
```

### 2. Log Aggregation

Aggregation centralizes log events across all services into a single queryable index. The pattern below routes each service's events into a per-service index while exposing a `logs-*` wildcard for cross-service queries.

```python
from elasticsearch import Elasticsearch
import json

class LogAggregator:
    def __init__(self, es_host):
        self.es = Elasticsearch([es_host])
        
    def index_log(self, log_entry):
        document = {
            **log_entry,
            '@timestamp': log_entry['timestamp']
        }
        
        self.es.index(
            index=f"logs-{log_entry['service']}",
            document=document
        )
        
    def search_logs(self, query):
        return self.es.search(
            index="logs-*",
            **query
        )
```

### 3. Log Analysis

Cross-service analysis requires aggregations at query time — not just retrieval. Error rate by service and log-level distribution are the baseline queries every pipeline should support.

```python
class LogAnalyzer:
    def __init__(self, es_client):
        self.es = es_client
        
    def analyze_service_logs(self, service_name, time_range):
        query = {
            'query': {
                'bool': {
                    'must': [
                        {'term': {'service': service_name}},
                        {'range': {'@timestamp': time_range}}
                    ]
                }
            },
            'aggs': {
                'log_levels': {
                    'terms': {'field': 'level'}
                },
                'error_rate': {
                    'filter': {'term': {'level': 'ERROR'}}
                }
            }
        }
        
        return self.es.search(index="logs-*", **query)
```

## Integration Patterns

### 1. Service Mesh Integration

Service mesh sidecar proxies generate access logs automatically. Capture request ID, method, path, status, and duration at this layer so application code doesn't have to.

```python
class ServiceMeshLogger:
    def __init__(self, service_name, mesh_client):
        self.service_name = service_name
        self.mesh_client = mesh_client
        
    def log_request(self, request):
        log_entry = {
            'timestamp': time.time(),
            'service': self.service_name,
            'request_id': request.headers.get('x-request-id'),
            'method': request.method,
            'path': request.path,
            'status': request.status_code,
            'duration': request.duration
        }
        
        return self.mesh_client.log(log_entry)
```

### 2. Message Queue Integration

Async message processing breaks the synchronous request chain. Log queue name, message ID, status, and processing time at both producer and consumer to reconstruct the full event timeline.

```python
class MessageQueueLogger:
    def __init__(self, queue_client):
        self.queue_client = queue_client
        
    def log_message(self, message):
        log_entry = {
            'timestamp': time.time(),
            'queue': message.queue,
            'message_id': message.id,
            'status': message.status,
            'processing_time': message.processing_time
        }
        
        return self.queue_client.log(log_entry)
```

### 3. Database Integration

Slow queries cause latency spikes that appear in application logs without context. Log query type, duration, and rows affected at the database layer to close that gap.

```python
class DatabaseLogger:
    def __init__(self, db_client):
        self.db_client = db_client
        
    def log_query(self, query):
        log_entry = {
            'timestamp': time.time(),
            'database': query.database,
            'query_type': query.type,
            'duration': query.duration,
            'rows_affected': query.rows_affected
        }
        
        return self.db_client.log(log_entry)
```

## What Breaks in Production First

### 1. Log Structure

- Use a consistent field schema across all services — divergent field names make cross-service queries brittle
- Include all operationally relevant fields at emit time — retrofitting fields requires redeployment
- Maintain backward compatibility in schema changes — downstream consumers break silently on missing fields
- Follow OTel semantic conventions — standard field names let off-the-shelf tooling work without configuration

### 2. Log Management

- Implement log rotation — unbounded log files fill disks and kill services
- Set retention policies — define upfront how long each log category must be kept
- Monitor log volume per service — a cardinality explosion or debug log left on in production will exhaust storage
- Handle backpressure — when the aggregation layer is unavailable, collectors must buffer or drop with a defined policy

### 3. Security

- Sanitize sensitive fields before emission — PII in log pipelines is a compliance incident waiting to happen
- Implement access control on log indexes — not every operator needs access to audit and security logs
- Encrypt log data in transit and at rest — treat log pipelines as sensitive infrastructure
- Audit log access — log who reads logs, especially in regulated environments

## Implementation Guidelines

### 1. Service Configuration

```yaml
logging:
  distributed:
    enabled: true
    collection:
      - file
      - syslog
      - journald
    aggregation:
      - elasticsearch
      - loki
    storage:
      retention: 30d
      rotation: 1d
    security:
      encryption: true
      access_control: true
```

### 2. Monitoring

```yaml
monitoring:
  metrics:
    - log_volume
    - log_latency
    - storage_usage
    - query_performance
  alerts:
    - log_overflow
    - collection_failed
    - storage_critical
```

### 3. Analysis

```yaml
analysis:
  patterns:
    - error_correlation
    - performance_impact
    - security_events
  visualizations:
    - log_flow
    - error_distribution
    - performance_trends
```

## Common Challenges

### 1. Performance

- Log volume spikes under load — instrument collection throughput and set per-service emit rate limits
- Storage costs scale with verbosity — tiered retention and sampling at the aggregation layer reduce spend
- Query performance degrades on high-cardinality fields — index selectively, not everything
- Network overhead — high-frequency log emission over a slow link introduces latency; batch where possible

### 2. Reliability

- Log loss during collector restarts — persistent buffers on the collection agent prevent gaps
- Collection failures — the service should not fail if the log sink is unavailable; fire-and-forget, buffer, or drop
- Storage saturation — set storage alerts well before capacity limits, not at them
- Query timeouts — time-bound queries and index on the fields operators actually filter by

### 3. Maintenance

- Schema evolution — use additive changes only; removing or renaming fields breaks existing dashboards and alerts
- Tool upgrades — test aggregation pipeline upgrades against a sample of real log volume before rolling out
- Configuration drift — treat logging config as code; review changes in pull requests
- Version management — pin collector and agent versions; silent behavior changes in log parsers are hard to debug

The practical next step is threading trace IDs through log emission so cross-service correlation works by default — that's covered in the how-to below.

- [Wiring Trace IDs into Logs](/howtos/wire-trace-ids-into-logs/) — the practical implementation of log-trace correlation
- [Structured Logging: Making Your Logs Machine-Readable](/guides/structured-logging-machine-readable/) — how to structure log output for automated analysis
- [Your Sampling Strategy Is Lying to You](/guides/sampling-strategy/) — why not all log data should be kept at equal fidelity
