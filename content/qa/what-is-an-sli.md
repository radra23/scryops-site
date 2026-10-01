---
title: "What is an SLI and how do you choose one?"
date: 2026-10-01
draft: false
answer: "An SLI (Service Level Indicator) is a quantitative measure of some aspect of your service's behaviour from the user's perspective. The best SLIs measure what users actually care about — not server-side proxies. Choose the metric that, when it degrades, users notice."
excerpt: "An SLI is a quantitative measure of service behaviour from the user's perspective. Choose the metric that, when it degrades, users notice — not server-side proxies that feel measurable but don't map to user experience."
readtime: 3
tags: ["SLOs", "Reliability", "Observability"]
---

**Q: Everyone says to "pick good SLIs" before setting SLOs. What actually counts as an SLI, and how do I choose one?**

An SLI is a number that says how well your service is treating its users right now. It's the bottom link in a chain. The SLI is what you measure. The SLO is the target you set for it, like 99.9% over 30 days. The error budget is the gap between that target and perfect, and it's what your burn-rate alerts spend. Get the SLI wrong and every link above it is precise about the wrong thing.

**Write it as a ratio.** The most useful shape, and the one Google's [SRE Workbook](https://sre.google/workbook/implementing-slos/) recommends, is good events divided by valid events. Successful requests over all requests. Requests served in under 300 ms over all requests. A ratio always lands between 0% and 100%, so an SLO is just a line on it and the error budget falls straight out. That's also why "p95 latency" makes an awkward SLI. Turn it into "the share of requests faster than 300 ms" and you can set a target on it and spend a budget against it.

**Then apply one test: would a user notice?** If the number got worse, would someone using your product feel it? Error rate passes. A failed checkout is about as noticeable as it gets. Latency passes. So does data freshness for a dashboard that's showing yesterday. CPU at 90% fails. Users don't feel your CPU. They feel the slow page it might cause, so measure the slow page. Memory, queue depth and pod restarts are the same kind of thing: useful for diagnosis, wrong for an SLI.

**Which SLIs fit depends on what the service does.** The Workbook sorts them by service type:

| Service type | SLI | Good event |
|---|---|---|
| Request-driven (APIs, web) | Availability | Request succeeded |
| | Latency | Request faster than a threshold |
| Pipeline (batch, streaming) | Freshness | Data updated within a threshold |
| | Correctness | Output record is right |
| Storage | Durability | Written data can be read back |

Most request-driven services need just two: availability and latency. Start there. For pipelines, batch jobs, queues and the rest, [the SLI matrix](/guides/sli-selection-by-service-type/) has a PromQL example for each.

**Measure as close to the user as you can.** Your load balancer sees failures your app never logs, like timeouts and crashed pods. So a ratio from load balancer metrics beats one from a single service's logs. Client-side measurement gets closer still, but it's noisier. Pick the closest point you can measure reliably.

Pick one or two SLIs per user journey, write each one as good over valid, and check that it would move if users got hurt. The [SLOs and error budgets guide](/guides/slos-and-error-budgets/) covers the targets and budgets built on top. When you're ready to alert on them, [this how-to](/howtos/set-up-slo-burn-rate-alerts/) turns an availability SLI into Prometheus burn-rate rules.
