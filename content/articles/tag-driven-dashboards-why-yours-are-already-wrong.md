---
title: "Your Dashboard Was Correct the Day You Wrote It"
date: 2026-06-16
draft: true
excerpt: "A hand-built dashboard is a snapshot of what your system looked like when you built it. The moment services change, tags shift, or a new team deploys something new, it starts lying. OpenTelemetry semantic conventions are the right interface for generating dashboards that stay true."
readtime: 6
tags: ["Observability", "OpenTelemetry", "Monitoring", "Best Practices"]
---

<!--
ARTICLE: Editorial opinion piece. The thesis is that hand-built dashboards decay
immediately — they're authored against a system state that no longer exists by
the time anyone reads them. The fix isn't better discipline about updating
dashboards; it's generating them from the tags your services already emit.

VOICE: Tech storyteller. Lead with the human cost (the 2am incident where the
dashboard showed the wrong service graph because someone renamed a deployment
three sprints ago). Build to the idea that OTel semantic conventions are already
a structured description of what a service IS — and a structured description of
what a service is IS a dashboard spec, if you know how to read it.

STRUCTURE:
1. The dashboard graveyard — open with the familiar failure: dashboard written
   at launch, never updated, full of panels that query metrics that no longer
   exist, missing the three services added last quarter. Everyone has one.

2. Why this happens (it's not laziness) — dashboards are authored at a moment
   in time and have no mechanism for staying current. Service topology changes
   every sprint. Metric names get refactored. Teams are added. The dashboard
   has no way to know.

3. The insight: your tags already describe your system — OTel semantic
   conventions are a structured vocabulary for what a service IS:
   - service.name + service.version tells you it needs a service overview
   - db.system tells you it needs a database latency/connection dashboard
   - k8s.deployment.name tells you it needs pod health panels
   - http.route tells you it needs endpoint performance breakdown
   This is not metadata about telemetry. This is a dashboard spec, written
   automatically by the act of instrumenting the service.

4. The rule-based case (don't overcomplicate it) — most of the value comes from
   a straightforward tag→template mapping. No ML required. The hard part is
   having the semantic conventions on your spans in the first place. Once you
   do, a lookup table gets you 80% of the way.

5. Where rule-based breaks down — custom business metrics, cross-service
   correlation views, executive-level aggregations. These require human
   authorship because no convention describes "conversion rate" or "revenue
   per deployment." The argument is not that you never write a dashboard by
   hand — it's that the operational baseline shouldn't require it.

6. Close: the team that never has a stale dashboard isn't more disciplined.
   They're generating from conventions, and every new service arrives with its
   monitoring already in place.

THINGS TO AVOID:
- Don't pitch any vendor or product
- Don't use the term "Dashboard as a Service" — too marketing-y
- Don't imply ML is needed for the core case
- Don't mention the PRD this concept came from

GOOD ANALOGIES:
- Dashboard as a passport: it describes the service, but it was issued on a
  specific date and expires. Generating from tags is like having a passport
  that renews itself.
- Or: a hand-built dashboard is a painting of your system. A tag-driven
  dashboard is a mirror.

MERMAID DIAGRAM IDEA:
Show the gap between "service topology at dashboard creation" vs "service
topology six months later" — new services missing from the dashboard, renamed
services showing as broken panels, removed services still showing as blank.

INSIGHT BOX:
The insight box should make the practical point: OTel semantic conventions
are stable across providers. A dashboard template written against
`db.system = "postgresql"` works whether the spans come from the OTel Python
SDK, the Java auto-instrumentation agent, or a manual instrumentation layer.
That portability is the other half of the value.

CROSS-LINK TO:
- The guide: content/guides/otel-semantic-conventions-dashboard-mapping.md
  (the reference mapping — what each tag implies about which panels to generate)
- The how-to: content/howtos/generate-dashboard-from-otel-tags.md
  (once the article convinces them, the how-to shows them how)
-->
