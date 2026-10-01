---
title: "Choosing SLIs for Your Service: A Practitioner's Matrix"
date: 2026-10-01
draft: false
excerpt: "Availability and latency are the obvious SLIs. But they don't fit every service type. This guide provides SLI selection frameworks for APIs, data pipelines, batch jobs, storage systems, event-driven services, and more."
readtime: 9
tags: ["SLOs", "Reliability", "Observability", "Metrics"]
---

Availability and latency are the SLIs everyone reaches for first, and for a request-driven API they're the right answer. Then you try them on a nightly batch job and they stop making sense. A batch job has no requests. A Kafka consumer has no response time anyone waits on. A model server can answer every request in 40 ms while serving predictions from a model that went stale last month.

This guide is the matrix: for each common service type, which SLIs fit, what counts as a good event, and a PromQL example you can adapt. If you want the basics first, [What is an SLI and how do you choose one?](/qa/what-is-an-sli/) covers them in three minutes, and [SLOs and Error Budgets](/guides/slos-and-error-budgets/) covers the targets and budgets you build on top.

## The Rules Every SLI Here Follows

Four rules, and every row in the matrix below obeys them.

**It's a ratio of good events to valid events.** That's the shape the [SRE Workbook](https://sre.google/workbook/implementing-slos/) recommends, and it's what makes an error budget fall out of an SLO. Where a service has no natural "event," like a pipeline's output or a batch job's last run, you make one: each minute where the data is fresh counts as a good minute.

**A user would notice if it got worse.** If the number can drop without anyone feeling it, it's a diagnostic metric, not an SLI.

**It's measured as close to the user as you can manage.** The load balancer beats the app's own logs. The consumer beats the queue. The reader beats the writer.

**"Valid" is a decision, so make it on purpose.** A 404 for a page that doesn't exist isn't your failure, so it can leave the denominator. A 429 from your own rate limiter is a user who didn't get served, so it stays in. Health checks and synthetic probes come out of request SLIs, or they quietly pad your success rate.

## The Matrix

| Service type | SLIs | Good event | Measure at |
|---|---|---|---|
| Synchronous API | Availability, latency | Response not 5xx; response under threshold | Load balancer or server span |
| Event-driven / async | End-to-end latency, delivery | Processed within threshold of publish; not dead-lettered | Consumer, against publish time |
| Streaming pipeline | Freshness, completeness | Output newer than threshold; records out match records in | Output side |
| Batch job | Freshness of last success | Last successful run within its window | Job completion |
| Storage | Durability, availability, latency | Written data reads back; operation succeeds in time | Prober and client |
| ML inference | Availability, latency, model freshness | Prediction served in time; model newer than threshold | Serving layer |
| CDN / static assets | Availability, latency at the edge | Asset fetched successfully in time | Client or external probe |

Most services need two of these, not five. Pick the ones that match how users actually get hurt.

## Synchronous APIs

This is the easy one. Availability is the share of requests that didn't fail on your side. With OpenTelemetry HTTP metrics, that's:

```promql
sum(rate(http_server_request_duration_seconds_count{job="checkout-api", http_response_status_code!~"5.."}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{job="checkout-api"}[5m]))
```

Latency is the share of requests faster than a threshold, read straight off the histogram:

```promql
sum(rate(http_server_request_duration_seconds_bucket{job="checkout-api", le="0.25"}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{job="checkout-api"}[5m]))
```

One catch: the threshold has to be one of the histogram's bucket boundaries. The OpenTelemetry default buckets for `http.server.request.duration` include 0.1, 0.25, 0.5 and 1 seconds, so 250 ms works and 300 ms doesn't. Pick your threshold from the buckets you have, or change the buckets.

## Event-Driven and Async Services

Here's the trap. Nobody waits on a consumer's response time. They wait for the order confirmation email, which arrives after the message sat in a queue, got picked up, and got processed. OpenTelemetry's `messaging.process.duration` only covers the processing part. A consumer that processes every message in 20 ms while the queue backs up for an hour looks perfect on that metric.

So measure from publish to done. Have the producer stamp the publish time on the message, and have the consumer record how long it took to finish in a histogram. That's a custom metric, so name it for what it is:

```promql
sum(rate(order_events_end_to_end_seconds_bucket{le="60"}[5m]))
/
sum(rate(order_events_end_to_end_seconds_count[5m]))
```

That's the share of order events fully handled within a minute of being published. For delivery, count what fell out the bottom: messages that ended up in the dead-letter queue, against all messages consumed. Consumer lag in messages, like `kafka_consumergroup_lag`, is a decent early warning. It's a poor SLI, though, because a lag of 10,000 messages means seconds on one topic and hours on another.

## Streaming Pipelines

A pipeline's users care about two things: is the data recent, and is it all there. Freshness is the first. Have the pipeline export the timestamp of the newest data it has fully written, then count the minutes where that's within your threshold:

```promql
avg_over_time(
  ((time() - max(pipeline_output_watermark_timestamp_seconds{pipeline="orders-etl"})) < bool 900)[1h:1m]
)
```

That's the share of minutes in the last hour where the output was less than 15 minutes old. Swap `[1h:1m]` for the SLO window you report on.

Completeness is the second. Compare records out with records in over the same window. A pipeline that's fresh but silently drops 2% of its input is fresh and wrong. This one usually runs as a periodic check against the source, not a live counter, and that's fine. Not every SLI has to come from a scrape.

## Batch Jobs

Duration and success rate sound right and mostly aren't. A nightly job that fails at 01:00 and succeeds on retry at 02:00 hurt nobody. A job that "succeeds" every night but finishes after the 06:00 report goes out hurt everybody.

What users care about is whether the output was ready when they needed it. That turns a batch SLI into freshness of the last success. The Prometheus convention for batch jobs is to push a last-success timestamp when the job finishes, and the SLI reads it:

```promql
(time() - max(batch_job_last_success_timestamp_seconds{job="nightly-billing"})) < bool (26 * 3600)
```

That's 1 while the last good run is less than 26 hours old, a day plus slack for a slow night, and 0 once a run is truly missing. Average it over your window the same way as the pipeline example.

## Storage Systems

Availability and latency per operation work like an API's: successful reads over all reads, fast writes over all writes. Durability is the hard one, because data loss is silent until someone asks for the data. The only honest way to measure it is to ask. Run a prober that writes known records, reads them back later, and counts how many came back intact. Successful read-backs over attempted read-backs is your durability SLI. It's a custom metric, and it's worth the effort. It's the one number that tells you your backups and replication actually work.

## ML Inference

The serving side is an API, so availability and latency apply as-is. The part that's specific to models is that a model can serve fast, valid-looking answers while being wrong. Freshness catches the common version of that. Export when the serving model was trained, and treat the model's age the same way as pipeline freshness: the share of time the model was newer than your threshold.

Accuracy is the one everybody wants and few can alert on. The ground truth usually arrives days later: the fraud was confirmed, the customer churned. So track accuracy as a slow quality SLO you review weekly, not as something you page on with a burn-rate alert.

## CDN and Static Assets

The tempting SLI is cache hit rate. Skip it. A 70% hit rate with a fast, healthy origin is invisible to users. A 99% hit rate while the edge returns errors is very visible. Hit rate is a cost metric. Measure what users get: availability and latency of fetching the asset, from outside your network. An external probe with the blackbox exporter does it:

```promql
avg_over_time(probe_success{job="blackbox", instance="https://cdn.example.com/app.js"}[1h])
```

That's the share of probes in the last hour that fetched the asset. If you run RUM, its resource timings measure the same thing from real users' browsers, across far more locations than a handful of probes.

## SLI Anti-Patterns

**Resource metrics.** CPU, memory, disk, pod restarts. Useful when you're debugging. Users don't feel any of them directly.

**The health check endpoint.** `/healthz` returns 200 while every real request fails on a broken database connection. It's measuring whether the process is alive, not whether it's useful.

**Averages.** Mean latency hides the slow tail where unhappy users live. Use the share of requests under a threshold instead.

**Per-instance SLIs.** One pod at 50% errors in a fleet of 20 is a 2.5% problem for users. Aggregate across the fleet at the level users experience.

**Counting traffic you generated.** Synthetic probes and health checks in the denominator inflate the success rate with requests that were always going to work.

## Composite SLIs for User Journeys

A checkout journey touches the cart, pricing, payment and orders services. If each one is 99.9% available and a request needs all four, the journey is only about 99.6% available: 0.999 multiplied by itself four times. That's the arithmetic of serial dependencies, and it's why SLOs on internal services don't add up to the experience users get.

The fix is to measure the journey where it starts. If checkout is one request to an API gateway, that request's success rate is the journey's availability, with every dependency already folded in. If it's several user-facing steps, a synthetic probe that walks the whole journey gives you one number for it. Keep the per-service SLOs as engineering targets for the teams that own them. Put the user-facing SLO on the journey.

## See Also

- [What is an SLI and how do you choose one?](/qa/what-is-an-sli/) — the short version, with the "would a user notice?" test
- [SLOs and Error Budgets](/guides/slos-and-error-budgets/) — targets, budgets and burn rates for the SLIs you pick here
- [How to Set Up Your First SLO and Burn Rate Alerts](/howtos/set-up-slo-burn-rate-alerts/) — turning an availability SLI into Prometheus alert rules
- [What is synthetic monitoring, and how does it differ from RUM?](/qa/synthetic-monitoring-vs-rum/) — the two ways to measure from the user's side
