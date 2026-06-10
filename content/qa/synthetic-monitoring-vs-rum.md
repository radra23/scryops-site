---
title: "What is synthetic monitoring, and how does it differ from RUM?"
date: 2026-06-10
draft: false
excerpt: "Synthetic monitoring runs scripted tests on a schedule; RUM captures what real users actually experience. They answer different questions and you need both."
readtime: 3
tags: ["Observability", "RUM", "Monitoring", "Reliability"]
---

**Q: I keep seeing "synthetic monitoring" alongside RUM. Are they the same thing? When do I need each one?**

They solve opposite problems, and the distinction matters when something breaks.

**Real User Monitoring (RUM)** instruments actual user sessions in browsers and mobile apps. It captures what real people experience: their device, their network, their location, the exact Core Web Vitals scores their session produced. RUM data is rich, varied, and only exists for traffic that actually arrives. If no one is using your service at 3am, RUM produces no data.

**Synthetic monitoring** runs scripted user journeys on a schedule from known locations, regardless of whether real users are present. A script logs in, navigates to checkout, adds an item, and completes a purchase — every five minutes, from London, Frankfurt, and Singapore simultaneously. It does not depend on real traffic.

Synthetic catches outages before users do. If your authentication service is down at 3am and no real users are awake to trigger RUM data, a synthetic check running every five minutes will fire within minutes of the failure — before business hours, before user complaints, before the support queue fills up. For SLA validation ("we guarantee 99.9% uptime from these five regions"), synthetic is the only signal that can directly measure the guarantee.

RUM catches degradation that synthetic misses. A synthetic test runs one scripted path at one simulated network speed. Real users arrive on iOS 17 on a congested 4G network, with browser extensions installed, and hit a rendering bug that only manifests on that combination. Synthetic tests can't anticipate the diversity of real sessions — RUM captures it automatically.

The practical consequence: an outage that synthetic detects but RUM doesn't means you caught it before users did. An experience degradation that RUM detects but synthetic misses means the problem only manifests for real users with real device and network variation. 
**When you only have one:** start with synthetic. It gives you availability monitoring with no dependency on user traffic, and availability failures are the most operationally urgent. Add RUM when you want to understand user-perceived performance across real device and network conditions — you need hundreds of sessions per cohort per day for percentile distributions to be meaningful.

**When to use both:** anything with an SLA or a user experience SLO. Synthetic validates availability; RUM validates quality of experience for real users. An availability SLO of 99.9% is a synthetic claim. A Core Web Vitals target of LCP under 2.5 seconds at p75 is a RUM claim.

Without synthetic, you learn about outages from user complaints. Without RUM, you can confirm the service responds but not whether the experience real users receive is acceptable.

<!-- TODO: Add Q&A on synthetic monitoring tooling: Grafana Synthetic, Checkly, k6 browser tests -->
<!-- TODO: Cross-reference to rum-and-core-web-vitals.md and rum-the-missing-signal.md -->
