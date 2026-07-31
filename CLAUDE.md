# scryops-site

Independent observability engineering publication. Hugo static site with a custom `scryops` theme.
Site: https://scryops.dev/

## Commands

```bash
hugo server          # dev server at http://localhost:1313 (live reload)
hugo                 # build to /public
hugo new guides/my-guide.md   # scaffold from archetype

python3 scripts/normalize-tags.py          # validate tag casing (runs as pre-commit check)
python3 scripts/normalize-tags.py --fix    # auto-correct casing in-place
python3 scripts/normalize-tags.py --list   # print all valid tags
```

## Content Sections

| Section | Path | Purpose | readtime |
|---------|------|---------|----------|
| Articles | `content/articles/` | Editorial opinion, big-picture takes | 5–7 min |
| Guides | `content/guides/` | In-depth technical references | 8–12 min |
| How-tos | `content/howtos/` | Step-by-step task walkthroughs | 5–8 min |
| Q&A | `content/qa/` | Short question-and-answer format | 2–3 min |

## Required Frontmatter

All content files must include:

```yaml
---
title: "..."
date: YYYY-MM-DD
draft: true        # true for migrated/unfinished content
excerpt: "..."      # used in listing cards and meta description
readtime: 7         # integer, minutes to read
tags: ["Observability", "Logs"]
---
```

Tags must come from the canonical list in `scripts/normalize-tags.py`. The pre-commit hook rejects unknown tags. To add a new tag, append it to `CANONICAL_TAGS` in that file.

## Shortcodes

```
{{< mermaid >}} ... {{< /mermaid >}}     # Mermaid diagrams — do NOT use raw ```mermaid fences
{{< insight >}} ... {{< /insight >}}      # Callout/insight box
{{< quote_with_author author="..." title="..." image="/images/..." >}} ... {{< /quote_with_author >}}
```

**Critical:** Hugo does not render raw ` ```mermaid ``` ` fences. Always use the `{{< mermaid >}}` shortcode.

## OTel Correctness Gotchas

These errors appear in external content and must be caught during review:

- **Burn rate math:** 14× fast burn over 30 days exhausts the budget in ~2.1 days (~51 hours), **not 2 hours**.
- **Jaeger exporter deprecated:** Removed in otelcol-contrib v0.86. Use `otlp/jaeger` exporter pointing to `jaeger:4317` (Jaeger accepts OTLP natively since v1.35).
- **OTel Collector image:** For OTTL transforms and most real configs, use `otel/opentelemetry-collector-contrib`, not `otel/opentelemetry-collector`.
- **No `OTEL_SERVICE_VERSION` env var:** there is no `OTEL_SERVICE_VERSION` environment variable. Set the version as a resource attribute — via the `"service.version"` key or the `SERVICE_VERSION` constant (which *is* exported by `opentelemetry.sdk.resources`) — or with `OTEL_RESOURCE_ATTRIBUTES=service.version=...`.
- **Tail sampling policy order:** The `tail_sampling` processor uses OR semantics — all policies are evaluated, a trace is kept if **any** policy returns sampled. Order does not determine which policy wins.
- **Trace-ID affinity:** Use `loadbalancingexporter` for routing traces to the same Collector replica. The `routing connector` does not provide trace-ID affinity.
- **OTTL SHA256:** `SHA256()` requires otelcol-contrib v0.96+. Note the version requirement when documenting it.

## Architecture

```
hugo.toml               site config (baseURL, menus, markup settings)
content/                all markdown content (sections above)
themes/scryops/         custom theme
  layouts/shortcodes/   mermaid.html, insight.html, quote_with_author.html, ...
  layouts/_default/     base templates
assets/                 CSS/JS source
static/                 static files served at root
scripts/                normalize-tags.py (tag validation)
archetypes/             hugo new templates per section
docs/                   legacy/migrated docs (not served — content moved to content/)
```

Markup config (`hugo.toml`) enables unsafe HTML, which is required for shortcode output.

---

# Telemetry reading system — design brief

> The standing brief for **design decisions** on scryops. `INTEGRATE.md` (in the
> handoff) is *how to install*; this is *how to decide*. On any design conflict,
> this section wins. Adapted from the Telemetry GUIDELINES handoff, with
> token/class names reconciled to the actual `themes/scryops/assets/css/telemetry.css`.

## The one job
**Read better.** Every decision serves sustained legibility for long, code- and
diagram-heavy technical pieces. Character is allowed only when it does not cost
reading comfort.

## Non-negotiables (do not regress)
1. **Reading face ≠ mono chrome.** Body copy is the reading face (`--font-read`,
   Courier Prime). Monospace (`--font-code`, IBM Plex Mono) is for code, labels,
   eyebrows, and UI chrome only — never long body copy.
2. **One measure for prose, wider for evidence.** Prose holds the reading
   measure; on reading pages `.layout .article` keeps prose at **680px**
   (centered) while evidence breaks wider (`.prose > .highlight, .prose > figure,
   .prose > table { max-width: none }`). The no-TOC layout is 820px to give room.
3. **Body ≥ 16px, generous line-height.** `--fs-body` ≥ 16px (currently 16px),
   `--lh-body` ~1.78. Never shrink body to fit more on screen.
4. **Two-track contrast.** Body ≥ WCAG AA (4.5:1) in every theme. Figure/diagram
   labels are held brighter (~10:1) and never render below ~12px.
5. **The code well is always dark.** Light and calm do not override `--code-bg` /
   `--code-text`. Do not add a light-theme override for the code well.
6. **Never transition the var-bound root.** No CSS `transition` on `html` / `body`
   background or color — custom properties can't interpolate, so a transition
   sticks on the old value (dark-on-dark on switch). Theme changes are instant.
7. **Tokens, never hexes.** Every color/size/space comes from a custom property in
   `telemetry.css`. Never hard-code a hex in a template or new rule.

## Type
- **Display / headings** — `--font-display` Space Mono, weight 400, **lowercase**
  (CSS `text-transform`; author titles normally in Markdown). h1 29 / h2 20 /
  h3 16px. Hierarchy comes from size + the mono voice, not weight or color.
- **Reading** — `--font-read` Courier Prime. Lede 17.5px (`.lede`), body
  `--fs-body` (16px), letter-spacing via `--read-track`.
- **Code** — `--font-code` IBM Plex Mono. Inline `code` is a bordered chip; blocks
  render as Hugo Chroma (`.highlight` / `.chroma`) on the always-dark well.
  Multi-language code uses the `langswitch` shortcode.
- **Pixel** — `--font-pixel` Press Start 2P. Wordmark and tiny eyebrows ONLY,
  ≥10px. Never body.

## Color — restraint is the rule
`--cyan` = links / identifiers / diagram edges. `--green` = healthy / values /
brand & CTAs. `--violet` = OpenTelemetry / topic accent. `--warn` / `--danger` =
semantics. `--eco` (#7FB069) = permacomputing footprint signals ONLY. Each color
means one thing — don't decorate with them. A page is mostly text on background,
with color marking only links, code tokens, semantics, and diagram structure.

## Components (apply the existing class; don't reinvent)
- Headings `h1/h2/h3` (or `.h1/.h2/.h3`); page title `.title`.
- Prose: `p` inside `.prose`; lede `.lede`. Links: element `a` (cyan + hairline
  underline) — there is no `.lnk` class; Markdown links are styled by element.
- Inline code `code` (chip); code blocks `.highlight` / `.chroma`.
- Callouts `.callout.info|warn|danger` + `.callout-label` (mapped to log levels
  INFO/WARN/ERROR). Insight asides: `{{< insight >}}` → `.insight`.
- Figures `.obs-fig` + `figcaption` / `.obs-cap`; inline SVG uses `.node` /
  `.nlab` / `.edge` / `.arr` so it inverts across themes. Mermaid →
  `{{< mermaid >}}` → `.mermaid` (themed + re-rendered by `mermaid-init.js`;
  never raw ```mermaid fences).
- Tables: mono uppercase header, hairline rows, no zebra.
- TOC: `.toc` with `.toc a` / `.toc a.active` (scrollspy added by `toc.html`).

## Reading preferences (the accessibility contract)
The prefs panel is part of the system, not a bolt-on. Persisted in `localStorage`
under `scryops-prefs`; applied as classes on `<html>` by the FOUC guard before
first paint. Honor all of them:
- **Theme** — `dark` (default) / `light` / `calm` (warm, lower-stimulation dark
  for long sessions, still ≥ AA).
- **`pref-legible`** — swaps the reading face to Atkinson Hyperlegible + bumps body
  size, for low-vision and dyslexic readers. Never remove this option.
- **`pref-spacing`** — looser line-height + letter-spacing.
- **`pref-reduce`** — kills transitions/animation; also respect the
  `prefers-reduced-motion` media query independently.
- **`pref-lite`** — drops to system fonts and skips the Mermaid runtime; auto-enables
  on a data-saver / metered connection unless the reader has made an explicit choice.
- **`pref-mono`** — collapses every semantic hue onto the neutral `--mc-ramp-*` value
  ramp; the system's own honesty test — if a component goes ambiguous here, it was
  leaning on colour and needed another channel.

## Permacomputing posture (ongoing)
Built small, durable, honest about its cost — observability pointed at the
publication itself. Default to **no new dependency** and **no new bytes**; justify
each KB and library like a metric label. Prefer SVG over raster, static over
runtime, semantic HTML over framework. Keep the footprint badge honest: real
measured transfer, inspectable method, `--eco` green only. Awareness, not
greenwash.

## When you edit
- Small ask → change only that; don't redesign around it.
- Match the voice: lowercase mono headings, warm-but-rigorous copy, terminal
  flourishes used sparingly (a prompt line, not a costume).
- After any change touching theme / figures / code: toggle **dark / light / calm**
  both ways (no dark-on-dark, no flash, code well legible, diagram labels bright)
  and build clean with `hugo --gc --minify`.
