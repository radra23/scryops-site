---
title: "Colophon"
type: "page"
layout: "single"
description: "How this site is built, what it measures, and how we estimate its carbon footprint — stated openly, no greenwash."
---

Observability turned on its own publication. This page is the honest accounting:
how the site is built, what it loads, and how the footprint badge in the footer
arrives at its numbers. Awareness, not absolution.

<div class="colophon">
  <div class="co-cmd"><b>scry@ops</b>:~$ cat colophon.txt</div>
  <div class="co-row"><span class="co-k">generator</span><span class="co-v">Hugo · static HTML, no server runtime</span></div>
  <div class="co-row"><span class="co-k">delivery</span><span class="co-v">prebuilt files served as-is</span></div>
  <div class="co-row"><span class="co-k">analytics</span><span class="co-v"><a href="https://umami.is/">Umami</a> · cookieless, no personal data</span></div>
  <div class="co-row"><span class="co-k">offline</span><span class="co-v">service worker · reads from cache when the network drops</span></div>
  <div class="co-row"><span class="co-k">fonts</span><span class="co-v">all <span class="eco">self-hosted</span> — Space Mono, Courier Prime, IBM Plex Mono, Atkinson Hyperlegible, Press Start 2P (no CDN)</span></div>
  <div class="co-row"><span class="co-k">diagrams</span><span class="co-v">Mermaid via CDN <span class="eco">(self-host pending)</span></span></div>
  <div class="co-row"><span class="co-k">carbon</span><span class="co-v">estimated per visit — see <a href="#method">method</a></span></div>
</div>

## Method

The footprint badge in the footer measures **this page's real network
transfer** using the browser's [Performance API][perf] — the same
`resource` and `navigation` timing entries you'd read off any instrumented
service. It sums `transferSize` across every resource the page actually
pulled, then converts bytes to an estimated carbon figure:

```text
grams CO₂e  =  bytes ÷ 1e9  ×  0.81 kWh/GB  ×  442 gCO₂e/kWh
                            └ energy/GB ┘    └ grid intensity ┘
```

The two constants come from the [Sustainable Web Design model][swd]:
`0.81 kWh/GB` for total energy per gigabyte transferred, and `442 gCO₂e/kWh`
for the global average grid intensity. It's an approximation, not a meter —
treat it as an order-of-magnitude signal, the way you'd treat a sampled
trace rather than a billing record.

### What the number honestly leaves out

- **Repeat visits read lighter.** `transferSize` reflects the *network*, so
  cached assets count as ~0 on a return visit. That's correct — a returning
  reader really does pull fewer bytes — but it means the badge shows less
  than a cold first load.
- **Cross-origin assets report zero.** Resources served without a
  `Timing-Allow-Origin` header return `transferSize: 0`. Fonts are now all
  self-hosted and counted; what's still hidden is the CDN-loaded Mermaid library
  (diagram pages only) and the Umami analytics script. We treat that as a to-do,
  not a loophole: self-hosting them makes them both lighter *and* visible to the
  meter.
- **It stops at transfer.** Device energy, the request's share of data-center
  and network overhead beyond the per-GB model, and embodied hardware carbon
  are out of scope. For a rigorous figure, swap the two constants above for
  the [CO2.js][co2js] library.

The point isn't a precise gram count. It's the habit: a publication about
seeing your systems clearly should be able to see itself.

[perf]: https://developer.mozilla.org/en-US/docs/Web/API/Performance_API
[swd]: https://sustainablewebdesign.org/estimating-digital-emissions/
[co2js]: https://developers.thegreenwebfoundation.org/co2js/overview/
