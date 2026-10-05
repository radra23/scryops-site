---
title: "What is synthetic monitoring, and how does it differ from RUM?"
date: 2026-09-27
draft: false
answer: "Synthetic monitoring runs scripted user journeys on a schedule, so it catches outages even when nobody is using the service. RUM records what real users experience on their own devices and networks. Synthetic tells you the service is up. RUM tells you the experience is good. You need both."
excerpt: "Synthetic monitoring runs scripted tests on a schedule. RUM captures what real users actually experience. They answer different questions, and you need both."
readtime: 3
tags: ["Observability", "RUM", "Monitoring", "Reliability"]
card:
  title: "Synthetic monitoring vs. RUM"
---

**Q: I keep seeing "synthetic monitoring" alongside RUM. Are they the same thing? When do I need each one?**

No. They solve opposite problems, and the difference matters most when something breaks.

**Real User Monitoring (RUM)** instruments actual user sessions in browsers and mobile apps. It captures what real people experience: their device, their network, their location, the exact Core Web Vitals their session produced. RUM data is rich and varied, but it only exists for traffic that actually arrives. If nobody's using your service at 3am, RUM has nothing to say.

**Synthetic monitoring** runs scripted user journeys on a schedule from known locations, whether or not anyone real is around. A script logs in, goes to checkout, adds an item and completes a purchase. It does that every five minutes, from London, Frankfurt and Singapore at once. It doesn't need real traffic at all.

Synthetic catches outages before users do. If your authentication service goes down at 3am and nobody's awake to generate RUM data, a check that runs every five minutes fires within minutes of the failure. That's before business hours, before the complaints and before the support queue fills up. It also measures availability from the outside, which is what most uptime SLAs ("99.9% from these five regions") are written against.

RUM catches the degradation synthetic misses. A synthetic test runs a handful of scripted paths under a few network profiles. Real users show up on an older phone over congested 4G, with browser extensions installed, and hit a rendering bug that only appears on that exact combination. No script anticipates that much variety. RUM records it because it's watching the real sessions.

The practical upshot: an outage that synthetic catches and RUM doesn't means you found it before your users did. A slowdown that RUM catches and synthetic doesn't means the problem only shows up under real devices and real networks.

**When you only have one:** start with synthetic. It gives you availability monitoring that doesn't depend on user traffic, and availability failures are the most urgent kind. Add RUM when you want to understand how fast things feel across real devices and networks. Give it time, though. Percentiles need enough sessions in each cohort to settle, so low-traffic pages and rare devices will stay noisy for a while.

**When to use both:** anything with an SLA or a user-experience SLO. Synthetic checks that the service is up. RUM checks that the experience is good. An uptime SLA measured from five regions is a synthetic claim. A Core Web Vitals target of LCP under 2.5 seconds or INP under 200 ms at p75 is a RUM claim.

{{< obs-synthetic-vs-rum >}}

Without synthetic, you learn about outages from user complaints. Without RUM, you can prove the service responds, but not whether the experience your users actually get is any good.
