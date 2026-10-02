---
title: "Distributed Logging: Ten Services, One Story"
date: 2026-06-07
draft: false
excerpt: "When a request crosses ten services, you get ten log streams that share nothing but a timestamp you can't trust. How to collect them on every node, carry the trace ID through, ship them through the OpenTelemetry Collector, and notice when lines go missing."
readtime: 10
tags: ["Logs", "Observability", "OpenTelemetry", "Collector", "Kubernetes"]
---

Single-service logging is a solved problem. Distributed logging is not.

When a request touches ten services, each one writes its own log stream to its own destination, and those streams share nothing but a timestamp you can't fully trust. Correlating a failure across that span takes three things: a trace ID on every log line, one pipeline that gets every stream to the same place, and a schema the services agree on. Without them you're reading ten separate stories and guessing at the plot.

This guide is about the plumbing between "my service writes a log line" and "I can query every line from that request, across every service". If you want the basics first — what to log, at what level, in what shape — start with [Logging Foundations](/guides/logging-foundations/) and [Structured Logging: Teaching Machines to Read](/guides/structured-logging-machine-readable/).

## The Four Jobs of a Log Pipeline

Strip away the vendor diagrams and every distributed logging setup does four things:

- **Collect.** Get each line off the machine that wrote it, before the container dies or the file rotates away.
- **Process.** Parse it, attach where it came from (pod, namespace, node), pull the trace context into the right fields, drop or redact what shouldn't travel.
- **Store.** Keep it somewhere queryable, for as long as you actually need it and no longer.
- **Query.** Ask cross-service questions: every line for this trace ID, error rate by service, what changed after the deploy.

The first two jobs are where distributed logging is won or lost, and they're where the OpenTelemetry Collector earns its place. Storage and query are your backend's problem: Loki, Elasticsearch, OpenSearch, ClickHouse or a vendor. With the Collector in the middle, you can change that choice without touching a single service. For what to do with the logs once they're queryable, see [Log-Based Monitoring](/guides/log-based-monitoring/).

## Collection: Two Ways Off the Box

There are two ways to get logs out of a service, and most real systems use both.

**Write to stdout, let a node agent pick it up.** The service writes one JSON object per line to stdout. The container runtime writes that to a file on the node, and a Collector running on every node (a Kubernetes DaemonSet) tails those files. The service knows nothing about where its logs go, which is exactly what you want for third-party software, sidecars and anything you can't recompile.

**Export over OTLP from the SDK.** The service's OpenTelemetry SDK turns each log call into an OpenTelemetry log record and sends it straight to a Collector. The trace ID and span ID are fields of the record itself, so there's nothing to parse. The catch is maturity: at the time of writing the [OpenTelemetry status page](https://opentelemetry.io/status/) lists the logs signal as stable in .NET and Java, a release candidate in Go, and still in development in Python and JavaScript.

So in a mixed fleet, stdout plus a node agent is the floor everything can stand on, and OTLP export is the upgrade for the runtimes where it's ready. Either way, the logs end up in the same Collector pipeline as your traces and metrics.

Whichever route you take, the path from your logger to the index has more places to lose a line than it looks:

{{< obs-log-flow-topology >}}

Every one of those drop points fails silently. Nothing raises an exception in your service; the log line is just gone. The [last section](#knowing-when-lines-go-missing) covers how to see each one.

## Correlation: The Trace ID Goes on Every Line

Each log line has to carry trace context from the moment it's written. Without `trace_id` and `span_id`, nothing downstream can tie it back to a request, and cross-service correlation is a timestamp search.

The per-language integrations that do this for you — the .NET OTLP logger, the Java agent's MDC fields, Go's `otelslog` bridge, Python's logging instrumentation — are covered in [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/), along with the field names each one actually writes. Use those first.

For the stdout route, here's the shape the node agent below expects: one JSON object per line, with the trace context at the top level under the names OpenTelemetry's [trace context in non-OTLP log formats](https://opentelemetry.io/docs/specs/otel/compatibility/logging_trace_context/) spec gives them. A stdlib-only Python formatter does it in a few lines:

```python
import json
import logging
import sys
from datetime import datetime, timezone

from opentelemetry import trace

SERVICE_NAME = "checkout-api"


class JsonLineFormatter(logging.Formatter):
    """One JSON object per line, trace context under the OTel spec names."""

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
                                 .isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "message": record.getMessage(),
            "service.name": SERVICE_NAME,
            **getattr(record, "fields", {}),
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:                       # outside a span: no fields at all
            line["trace_id"] = format(ctx.trace_id, "032x")
            line["span_id"] = format(ctx.span_id, "016x")
            line["trace_flags"] = format(ctx.trace_flags, "02x")
        if record.exc_info:
            line["exception.stacktrace"] = self.formatException(record.exc_info)
        return json.dumps(line)


handler = logging.StreamHandler(sys.stdout)   # stdout: the node agent reads it
handler.setFormatter(JsonLineFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
log = logging.getLogger("checkout")

# Inside a request span (created by your HTTP instrumentation):
#   log.warning("payment retry", extra={"fields": {"order.id": "ord_12345"}})
```

Run under `opentelemetry-sdk` 1.45 on Python 3.12, a call inside a span prints:

```json
{"timestamp": "2026-10-02T18:10:12.290+00:00", "level": "WARNING", "message": "payment retry", "service.name": "checkout-api", "order.id": "ord_12345", "trace_id": "30b192f0a2919202359f107ddaf92013", "span_id": "5d26a48f7cb13876", "trace_flags": "03"}
```

Three details carry the weight. The timestamp is ISO 8601 with a UTC offset, not a float of epoch seconds, so nothing downstream has to guess its unit. The trace fields are left out entirely outside a span, instead of written as zeros that match every other orphaned line. And `trace_flags` is `03` rather than `01` because current SDKs also set the W3C Trace Context Level 2 "random trace ID" bit alongside "sampled". Don't write queries that expect `01`.

The trace ID only connects services if the *next* service continues the same trace. That's context propagation, not logging, and it breaks in predictable places: uninstrumented HTTP clients, message queues where the producer never injects the context, background workers that started outside any request. [Context Propagation](/guides/otel-context-propagation/#where-propagation-breaks-between-services) walks through each one. If two services' logs for the same request show different trace IDs, the bug is there, not in your logger.

{{< insight >}}
**Don't sort a request by timestamp.** Clocks on different nodes drift, and a downstream service can log a line that appears to come before the upstream call that caused it. Put the lines in order by the trace's span tree — parent before child — and use timestamps only within one service.
{{< /insight >}}

## The Node Agent: One Collector Per Node

This is the Collector that tails container logs on every Kubernetes node, turns the JSON lines above into proper OpenTelemetry log records, and forwards them to a gateway. Use the `otel/opentelemetry-collector-contrib` image: the `filelog` receiver and the `file_storage` extension aren't in the core distribution.

```yaml
# otel/opentelemetry-collector-contrib, one per node (DaemonSet).
# Mount /var/log/pods read-only and /var/lib/otelcol as a hostPath volume.
extensions:
  file_storage:
    directory: /var/lib/otelcol/storage    # survives agent restarts

receivers:
  filelog:
    include: [/var/log/pods/*/*/*.log]
    exclude: [/var/log/pods/otel_*/*/*.log] # the Collector's own namespace
    include_file_path: true                 # the container operator needs it
    storage: file_storage                   # remember read offsets on disk
    operators:
      - type: container                     # unwrap CRI/Docker framing, add k8s.* resource attrs
      - type: json_parser
        if: 'body matches "^\\{"'           # leave non-JSON lines as plain text
        timestamp:
          parse_from: attributes.timestamp
          layout_type: gotime
          layout: "2006-01-02T15:04:05.000Z07:00"
        severity:
          parse_from: attributes.level      # INFO, WARNING, ERROR match by default
        trace:
          trace_id:
            parse_from: attributes.trace_id
          span_id:
            parse_from: attributes.span_id
          trace_flags:
            parse_from: attributes.trace_flags
      - type: move
        if: 'attributes["service.name"] != nil'
        from: attributes["service.name"]
        to: resource["service.name"]
      - type: move
        if: 'attributes.message != nil'
        from: attributes.message
        to: body

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 25
  batch: {}

exporters:
  otlp:                                     # renamed otlp_grpc in recent releases; otlp still works as an alias
    endpoint: otel-gateway.otel.svc:4317
    sending_queue:
      storage: file_storage                 # queue on disk, not in memory

service:
  extensions: [file_storage]
  pipelines:
    logs:
      receivers: [filelog]
      processors: [memory_limiter, batch]
      exporters: [otlp]
```

*Checked against the component READMEs in opentelemetry-collector-contrib; not run.*

The two `storage` lines are the ones that matter most. Without them, the receiver keeps file offsets in memory and the exporter keeps its retry queue in memory. Restart the agent — a deploy, an OOM kill, a node drain — and both are gone: you either re-read files from the end and skip what was written while the agent was down, or you lose whatever was queued for the gateway. With them, both pick up where they left off.

`start_at` is left at its default, `end`. That only governs files that are already there the first time the agent sees them; once an offset is stored, the agent resumes from it.

The parser does the job the [trace ID how-to](/howtos/wire-trace-ids-into-logs/#closing-the-loop--verify-its-working) describes from the other side: it moves the IDs out of the JSON and into the log record's own `TraceId`, `SpanId` and `TraceFlags` fields, where every OTLP backend looks for them. The `container` operator adds `k8s.namespace.name`, `k8s.pod.name` and `k8s.container.name` as resource attributes from the file path, so every line already says where it came from. And the order inside `processors` is not optional: `memory_limiter` comes first so the agent sheds load before it runs out of memory, and `batch` comes after it.

## The Gateway: One Place to Change Your Mind

The agents don't talk to the backend directly. They send to a small, horizontally scaled pool of gateway Collectors, and the gateway is the only thing that knows where logs end up:

```yaml
# Gateway: a Deployment behind a Service, same contrib image.
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 25
  batch: {}

exporters:
  otlphttp:                                 # Loki 3.x ingests OTLP natively; recent releases name this otlp_http
    endpoint: http://loki-gateway.loki.svc/otlp

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp]
```

*Checked against the component READMEs and Grafana's Loki OTLP docs; not run.*

This tier is where shared policy belongs, because it's applied once, for every service. Redacting personal data is the obvious one: [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) explains why the Collector, not the application, is the right place for it. It's also where you'd add content-aware filtering when the volume starts to hurt; [High-Throughput Logging: Sampling, Collectors, and the Wire](/guides/high-throughput-log-pipelines/) covers that.

Logs don't need any routing between gateway replicas: any replica can handle any log record. The exception is when the same gateway also tail-samples traces. Every span of a trace then has to reach the same replica, and that takes a `loadbalancingexporter` tier in front, keyed on trace ID. [How to Configure OTel Collector Tail Sampling](/howtos/configure-collector-tail-sampling/#step-5-optional-scale-to-multiple-collectors) shows the setup. And remember the consequence: logs aren't sampled with their trace. If you keep 10% of traces, 90% of your trace IDs in logs point at traces that no longer exist. [Your Sampling Strategy Is Lying to You](/articles/sampling-strategy/) explains why tail sampling at least keeps the traces you'll actually look up.

## The Edges of Your Code: Mesh, Queues and Databases

Not every useful log line comes from your application.

**Service mesh access logs.** A mesh sidecar can log every request it proxies, with no application code at all. In Istio, the Telemetry API turns it on mesh-wide:

```yaml
apiVersion: telemetry.istio.io/v1
kind: Telemetry
metadata:
  name: mesh-default
  namespace: istio-system
spec:
  accessLogging:
    - providers:
        - name: envoy
```

*Checked against Istio's access logging docs; not run.*

The sidecar writes to its container's stdout, so the node agent above picks it up with everything else. Two caveats. The default format is text, not JSON (set `accessLogEncoding: JSON` in the mesh config if you want the agent to parse it). And it carries `x-request-id`, not the trace ID, unless you customise the format, so these lines join your application logs by request ID, not trace ID. The mesh also doesn't propagate trace context through your service for you: the application still has to forward the headers from inbound to outbound calls.

**Message queues.** An asynchronous hop is where request timelines fall apart. Log the queue name and message ID on both the producer and the consumer, and make sure the trace context travels in the message headers so both sides log the same trace ID. The propagation guide has [the inject and extract code](/guides/otel-context-propagation/#where-propagation-breaks-between-services) for each language.

**Databases.** A slow query shows up in application logs as a slow request with no explanation. Database client instrumentation records each query as a span, which is usually a better place for the statement and its duration than a log line. Log what the span can't tell you: the decision your code made because the query was slow or failed.

## What Breaks in Production First

Distributed pipelines tend to fail in a predictable order, and none of it is exotic.

{{< obs-what-breaks-first >}}

**Schema drift.** It surfaces on the first cross-service query. One service writes `user_id`, another `userId`, a third `user.id`, and the query that should cover all three covers one. Pick names once — OpenTelemetry's semantic conventions name most of what you need — and make schema changes additive only, because renaming a field silently breaks every dashboard and alert built on the old name. [Common Logging Pitfalls](/guides/common-logging-pitfalls/) catalogues the usual offenders, and [Log Context Enrichment](/guides/log-context-enrichment/) covers adding fields without taxing the request path.

**Retention and volume.** It surfaces with the first full disk or the first bill. Decide up front how long each kind of log has to be kept: audit and security logs often have a mandated minimum, debug output rarely needs more than days. Route by [log level](/guides/log-levels-and-severity/) and purpose rather than keeping everything for the longest period anyone asked for. Watch volume per service, because a single `DEBUG` left on in production can outrun the rest of the fleet.

**Access control.** It surfaces when someone asks who can read these. A log pipeline that carries audit logs, security events and the occasional stray email address is sensitive infrastructure. Restrict who can query which streams, encrypt in transit (TLS between agent, gateway and backend) and at rest, and keep a record of who reads the audit logs.

## Knowing When Lines Go Missing

Every drop point in the figure at the top has a Collector metric. The Collector exposes its own telemetry in Prometheus format on port 8888 by default; scrape it like any other service. Depending on how your setup exports them, counters may carry a `_total` suffix.

| Drop point | Watch |
|---|---|
| Agent can't keep up or can't push into its pipeline | `otelcol_receiver_refused_log_records` |
| Sending queue full | `otelcol_exporter_queue_size` approaching `otelcol_exporter_queue_capacity`; `otelcol_exporter_enqueue_failed_log_records` |
| Gateway or backend rejecting, retries exhausted | `otelcol_exporter_send_failed_log_records` |
| Overall throughput | `otelcol_receiver_accepted_log_records` vs `otelcol_exporter_sent_log_records`, per hop |

Alert on the failure counters being non-zero, not on the queue being full: by the time the queue is full, you're already dropping. And compare accepted at the agent with sent at the gateway. A gap that grows means lines are disappearing somewhere between them.

One drop point no Collector metric can show: a file that rotates before the agent has read it. The kubelet rotates container logs by size, so a service that writes faster than the agent reads can lose lines without any counter moving. If a noisy service shows gaps that the metrics can't explain, look at its log rate first, and at whether it should be logging that much at all.

## Where to Go Next

The next step is making sure every service actually writes the trace ID, so cross-service correlation works by default rather than by luck. [How to Wire Trace IDs Into Your Logs](/howtos/wire-trace-ids-into-logs/) does that for .NET, Java, Go and Python. If logging itself starts showing up in your latency, [Async Logging](/guides/async-logging/) moves the writes off the request path.

Ten services, ten streams, one pipeline. That's the point where the logs finally tell one story.
