---
title: "Telemetry Data Sovereignty: Where Your Data Lives Matters"
date: 2026-10-01
draft: false
excerpt: "A system that spans continents produces telemetry that spans legal jurisdictions. Here's how to keep traces and logs where the law wants them, and still see your whole system."
readtime: 11
tags: ["Compliance", "Privacy", "GDPR", "Multi-Cloud", "OpenTelemetry", "Collector", "Observability"]
card:
  title: "Telemetry Data Sovereignty"
---

Your users are in Frankfurt. Your trace backend is in Virginia. Every span that carries a user ID, an IP address or an email is personal data, and every one of them just crossed an ocean.

Nobody decided that. Somebody picked a region for the observability cluster three years ago, and the telemetry followed. [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) covers getting personal data out of spans. This guide covers the data you can't, or won't, strip: where it's allowed to live, who's allowed to look at it, and how to build a pipeline that respects both without going blind.

{{< obs-telemetry-controls-map here="backend" >}}

## Telemetry Is Regulated Data Too

Residency law doesn't care what the data is *for*. If a span holds personal data, the rules that govern your customer database govern your trace backend too. Three details trip teams up.

**Access counts, not just storage.** Under the EDPB's [Guidelines 05/2021](https://www.edpb.europa.eu/system/files/2023-02/edpb_guidelines_05-2021_interplay_between_the_application_of_art3-chapter_v_of_the_gdpr_v2_en_0.pdf), a transfer happens when EU data is made available to a separate company or processor in a third country, and remote access on a screen counts. So an observability vendor's support team outside the EEA, or an offshore SRE contractor, querying your EU-hosted traces is a transfer, even though nothing was copied. Your own employee checking a dashboard from a hotel abroad isn't, because no second party is involved. The GDPR still applies to them.

**Hashing isn't an exemption.** Pseudonymised data stays personal data for you, because you hold the key (GDPR Recital 26). The Court of Justice ruled in [EDPS v SRB](https://curia.europa.eu/site/upload/docs/application/pdf/2025-09/cp250107en.pdf) (September 2025) that pseudonymised data may not be personal data for a *recipient* who can't reasonably re-identify it. That case was decided under the rules for EU institutions, and whether it helps you depends on facts like who holds the key and what else the recipient can link. Don't build an architecture on it.

**Real aggregates are out of scope.** Truly anonymous statistics fall outside the GDPR. A request counter labelled by service and templated route is anonymous. The same counter labelled by user ID isn't, and even a bounded label can identify someone if it narrows things down far enough, like a tenant ID or a country with a handful of users. The labels decide.

## What the Rules Actually Say

This is the landscape as of October 2026. It moves, so treat it as a map, not legal advice, and check it with your counsel.

| Jurisdiction | What it restricts | What it means for telemetry |
|---|---|---|
| EU / EEA (GDPR Chapter V) | Transfers out of the EEA need an adequacy decision (Art. 45) or safeguards such as Standard Contractual Clauses (Art. 46) | Personal telemetry leaving the EEA, or read from outside it by a vendor, needs a transfer mechanism for every flow |
| China (PIPL) | Exports need a CAC security assessment, certification or the standard contract (Art. 38). Critical infrastructure operators and large processors must store data in China (Art. 40) | Thresholds and exemptions since March 2024 mean small, non-sensitive flows may be exempt, but plan for in-country storage |
| Russia (152-FZ) | Russian citizens' personal data must be recorded and stored in Russian databases. Since 1 July 2025, using foreign databases for those operations is explicitly banned | Keep Russian users' telemetry in Russia. Cross-border transfers also need advance notice to Roskomnadzor |
| Germany | No general localisation law. Sector rules apply, such as [§ 393 SGB V](https://www.gesetze-im-internet.de/sgb_5/__393.html) for health data | "Data stays in Germany" usually comes from contracts and procurement, not statute |

A few of those rows need more than a table cell.

**The EU–US route is open but contested.** [Schrems II](https://curia.europa.eu/jcms/upload/docs/application/pdf/2020-07/cp200091en.pdf) (July 2020) struck down the Privacy Shield and left Standard Contractual Clauses standing, on condition that you check whether the destination's law lets them work, and add supplementary measures or stop the transfer if it doesn't. The EU–US Data Privacy Framework replaced the Privacy Shield with an adequacy decision in July 2023. The General Court [dismissed the first challenge](https://curia.europa.eu/site/upload/docs/application/pdf/2025-09/cp250106en.pdf) in September 2025, and the appeal is pending. In July 2026, after the US Supreme Court ruled that the president can remove FTC commissioners at will, the EDPB [asked the Commission](https://www.edpb.europa.eu/documents/edpb-correspondence/edpb-letter-to-the-european-commission-on-us-supreme-court-judgment_en) to look at what that means for the framework. It's in force today. Just don't build an architecture that only works if it stays that way.

**The exceptions won't carry a pipeline.** GDPR Article 49 has narrow fallbacks, like explicit consent, for specific situations. Its last resort covers non-repetitive transfers about a limited number of people. Continuous telemetry is the opposite of that.

**Russia tightened in 2025.** The 2015 localisation law already required Russian citizens' data to be stored in Russia. The [2025 amendment](https://www.lidings.com/media/legalupdates/localization_pd_update/) made the ban on foreign databases explicit and extended it to processors. Mirroring a copy into Russia while the primary lives elsewhere is now very hard to defend.

## The Architecture That Holds Up

There are three ways to build this, and most teams end up in the middle one.

**Regional silos.** Each region gets its own Collectors and its own backend, and nothing crosses. It's simple and compliant, and it leaves you blind to anything that spans regions.

**Regional data, global aggregates.** Full-fidelity traces and logs stay in the region that produced them. Only non-personal aggregates, like request rates, error rates and latency, leave for a global view. You keep one dashboard for the whole system, and the personal data never moves. That includes backups and disaster-recovery replicas: a replica in another region is a copy in another region.

**Routing by residency.** A shared gateway that serves tenants with different rules sends each tenant's data to the right regional backend, based on a tag on the data.

Retention is the other half of this stage. A trace you no longer hold can't be read from abroad, so keep full-fidelity data in each region only as long as you need it for debugging, and let the aggregates carry the long-term view.

{{< mermaid caption="Fig. — Full-fidelity telemetry (solid arrows) stays in its region. Only aggregate metrics with allowlisted labels (dashed arrows) leave for the global view." >}}
flowchart LR
    subgraph EU["EU region"]
        EUS[EU services] --> EUG[EU gateway Collector]
        EUG --> EUB[(EU trace and log backend)]
    end
    subgraph US["US region"]
        USS[US services] --> USG[US gateway Collector]
        USG --> USB[(US trace and log backend)]
    end
    EUG -.-> GM[(Global metrics)]
    USG -.-> GM
{{< /mermaid >}}

Route at the edge, in the region where the data is born. A central Collector *outside* that region, which receives everything and then sorts it, is already too late. The data crossed the border on its way in.

## Building It in the Collector

Here's an EU gateway that keeps full traces in the EU and sends only span metrics to the global backend:

```yaml
# EU gateway Collector: runs in the EU, receives EU services' telemetry.
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

connectors:
  # Turns spans into request/error/duration metrics. Only these leave the region.
  span_metrics:
    dimensions:
      - name: http.route
      - name: http.response.status_code

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 20

  # Allowlist, not blocklist: everything not named here stays behind.
  transform/leaving-region:
    metric_statements:
      - context: resource
        statements:
          - keep_keys(attributes, ["service.name", "deployment.environment.name"])

  batch: {}

exporters:
  otlp/eu-backend:                 # full-fidelity traces, stored in the EU
    endpoint: traces.eu.example.internal:4317
  otlp/global-metrics:             # aggregate metrics, any region
    endpoint: metrics.global.example.internal:4317

service:
  pipelines:
    traces/in-region:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/eu-backend, span_metrics]
    metrics/leaving-region:
      receivers: [span_metrics]
      processors: [transform/leaving-region, batch]
      exporters: [otlp/global-metrics]
```

We loaded this into `otelcol-contrib` 0.161.0 and sent it spans carrying an email address, a client IP, a user ID and a host name. The EU backend got every span, personal data included, which is fine in-region. The global backend got two metrics, `traces.span.metrics.calls` and `traces.span.metrics.duration`, with exactly two resource attributes and none of the personal values.

Two things make that work. The `keep_keys` statement is an allowlist for resource attributes, so a resource attribute someone adds next year stays home by default instead of leaking by default. And the labels on each data point are set by `dimensions`, here a templated route and a status code. `span_metrics` also adds `span.name` and the span's status, so the same rule covers span names. Use `http.route` (`/users/{id}`), never the raw URL, and keep span names low-cardinality, or the IDs come straight back in as labels. The connector is called `span_metrics` in current releases and `spanmetrics` in older ones.

Logs follow the same shape: a logs pipeline that exports to the regional backend, and nothing that leaves.

A shared gateway that serves tenants with different residency rules is the one exception, and only if it sits in the strictest jurisdiction they share. Then nothing that arrives is out of place, and the only data it sends on is data whose own rules allow it to go there. The `routing` connector does the sorting:

```yaml
# Shared gateway in the EU, serving tenants with different residency rules.
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

connectors:
  routing:
    # Untagged data stays in the EU. If a tag is missing, fail closed.
    default_pipelines: [traces/eu]
    table:
      - context: resource
        condition: attributes["data.residency"] == "us"
        pipelines: [traces/us]

exporters:
  otlp/eu-backend:
    endpoint: traces.eu.example.internal:4317
  otlp/us-backend:
    endpoint: traces.us.example.internal:4317

service:
  pipelines:
    traces/in:
      receivers: [otlp]
      exporters: [routing]
    traces/eu:
      receivers: [routing]
      exporters: [otlp/eu-backend]
    traces/us:
      receivers: [routing]
      exporters: [otlp/us-backend]
```

The important line is `default_pipelines`. Data with no `data.residency` tag, or a misspelt one, stays in the EU instead of drifting to wherever the default happens to point. In our test, 30 EU-tagged spans and 10 untagged ones landed in the EU pipeline, and exactly the 20 US-tagged spans went to the US. Set the tag at the source, as a resource attribute from the service's or tenant's configuration, so it's there before the data leaves the process.

One honest caveat: the `routing` connector and `span_metrics` are both Alpha in 0.161.0. The old routing *processor* is gone. Pin your Collector version and test upgrades before you roll them out.

## The Correlation Problem

The hard part isn't storage. It's the request that starts in Frankfurt and calls a service in Virginia.

Trace context still propagates, so both halves share a trace ID. A trace ID carries no personal values itself, but it's a join key: whoever holds both halves can stitch them back together. So don't copy one half across to make a complete trace. Query each regional backend for the trace ID and assemble the picture in the query tool, not in storage. Many tracing backends and dashboards can query several data sources at once, which gives you a combined view without a combined store.

That avoids a combined store. It doesn't avoid a transfer. Whoever runs the query sees the EU spans, so if the query tool or the person using it belongs to a separate company outside the EEA, that's a transfer by remote access. Run the query tool in-region, and limit who can use it to people allowed to see that data.

Exemplars need the same care. They link a metric point to a trace by carrying trace and span IDs, and sometimes a few span attributes. A global metrics store full of exemplars is a global store of join keys. `span_metrics` leaves exemplars off unless you turn them on, and in our test the metrics that left the region carried no trace IDs at all. Keep it that way for anything that crosses a border.

## Decide Per Signal

The quickest way to get unstuck is to stop asking "where does our telemetry go?" and ask it once per signal:

| Signal | Usually personal? | Default home |
|---|---|---|
| Traces | Yes: user IDs, IPs, URLs, payload fragments | The region that produced them |
| Logs | Yes, and less structured, so harder to scrub | The region that produced them |
| Metrics with bounded, non-identifying labels | No | Anywhere. These are your global view |
| Exemplars | Join keys to personal traces | With the traces, or dropped |

Then put the exceptions in writing. Each one is a decision someone will be asked about later.

## Write It Down

Regulators and auditors ask the same few questions, so answer them before they do:

- **Where each signal is stored**, region by region, including backups and the vendor's support access.
- **The transfer mechanism for every flow that crosses a border:** adequacy, Standard Contractual Clauses or an Article 49 derogation. Your GDPR record of processing activities has to list transfers to third countries anyway (Article 30(1)(e)).
- **Who can query each regional backend**, and from where. Log that access like any other access to personal data. [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) covers building that record.
- **The Collector configs themselves**, in version control and reviewed. A change to a routing table is a change to a compliance control.

## Where to Start

1. Find out where your telemetry actually lives today, including the vendor's regions and its support teams' locations.
2. Inventory which signals carry personal data. The attribute inventory from [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) is the place to start.
3. Stand up a gateway Collector in each region, and point that region's services at it.
4. Keep traces and logs in-region, and send only allowlisted aggregate metrics to the global view.
5. Tag data with its residency at the source, and make every routing default fail closed.
6. Write down each flow that crosses a border and its transfer mechanism, and review it whenever the law moves. In this area, it's moved several times since 2025.

## See Also

- [Observability Under Compliance](/guides/compliance-observability/) — GDPR, HIPAA, SOC 2 and PCI DSS and where telemetry sits in each
- [Your Traces Are Leaking User Data](/guides/pii-in-telemetry/) — getting personal data out of spans before it's stored anywhere
- [Data Masking in Telemetry](/guides/data-masking-in-telemetry/) — hashing, tokenising and coarsening, and why a hash isn't anonymous
- [Implementing Audit Trails with OpenTelemetry](/guides/audit-trail-implementation/) — recording who accessed what, wherever it lives
