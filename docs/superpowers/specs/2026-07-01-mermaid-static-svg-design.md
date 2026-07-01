# Pre-rendered static-SVG Mermaid diagrams

**Date:** 2026-07-01
**Status:** Approved design — pending implementation plan
**Branch:** `feat/mermaid-static-svg`

## Problem

Mermaid diagrams currently render client-side from a ~971 KB (gzipped) runtime
loaded lazily from a CDN on diagram pages. `baseof.html` injects
`https://cdn.jsdelivr.net/npm/mermaid@10.9.6` then `mermaid-init.js` (gated to
non-Lite pages that contain a `.mermaid` element). This violates the site's
permacomputing goals: it ships MB not KB, requires JS, pulls from a third-party
CDN, and inflates the per-page footprint the badge counts (~1 MB on diagram
pages).

There are **~52 `{{< mermaid >}}` diagrams across 24 content files**
(guides/howtos/qa/articles).

## Goal

Pre-render every Mermaid diagram to **static inline SVG at build time**, themed
to the Telemetry tokens so one SVG inverts across **dark / light / calm** with
**zero JS**. Then remove the CDN runtime, `mermaid-init.js`, and the unused
3.2 MB vendored `mermaid.min.js`. A diagram page's footprint should drop from
~1 MB to KB, and diagrams must render correctly with JS disabled.

## Decisions (locked)

1. **Render location — commit rendered SVGs, guard in CI.** A local script
   renders each diagram to a tokenized SVG committed to the repo, keyed by a
   content hash. CI stays **pure Python + Hugo 0.145** (the deploy installs no
   Node/Chromium); the existing `validate` Python job fails if any diagram's SVG
   is missing or stale.
2. **Theming — reuse the existing shared diagram tokens.** Map Mermaid
   nodes/edges/labels onto the same `--node-fill` / `--node-stroke` / `--edge` /
   `--nlab` CSS variables the `obs-*` figures already use. Defined for all three
   themes in `telemetry.css` (`:root`, `html.light`, `html.calm`). No new
   tokens. **Calm works for free** — the old `mermaid-init.js` never handled
   calm (it only branched on `.light`), so static SVG is strictly more correct.
3. **Fallback — no-JS shows the SVG; Lite shows the text source.** The SVG needs
   no JS, so no-JS visitors get the real diagram (a strict upgrade). Only
   Lite/data-saver mode swaps to the styled "diagram source" text block. The
   `{{< mermaid >}}` source stays in the markup for that Lite view.

## Architecture

Author writes `{{< mermaid >}}…{{< /mermaid >}}` unchanged. Pipeline:

```
content/*.md  ──►  render-diagrams.py  ──►  themes/scryops/assets/diagrams/<hash>.svg (committed)
   │  (mmdc render + Python tokenize)              │
   └──────────────── shortcode resources.Get ──────┘  ──► inline SVG in .diag-card
```

### Component 1 — Render + tokenize: `scripts/render-diagrams.py` (+ pinned `package.json`)

- Walk `content/`, extract every `{{< mermaid >}}` inner source.
- Key each diagram by `sha256(trim(source))[:12]` (hex). **The trim/hash rule is
  shared verbatim** with the shortcode and the CI guard — see "Hash contract".
- Render with `mmdc` (dev-only `@mermaid-js/mermaid-cli`, version-pinned in
  `package.json`; **not** installed in CI, **not** shipped):
  - `htmlLabels:false` — labels become themeable SVG `<text>`, not HTML
    `<foreignObject>`. **Load-bearing:** foreignObject labels cannot be tokenized
    the same way and degrade in some renderers.
  - transparent background.
  - a **sentinel palette**: one unmistakable, unique hex per role
    (node-fill, node-stroke, edge/line, label-text, cluster/subgraph
    background + border). Because
    we control the input palette, downstream substitution is deterministic across
    every diagram type without parsing Mermaid's DOM.
- Post-process each SVG in Python:
  - Replace each sentinel hex → `var(--node-fill)` / `--node-stroke` / `--edge` /
    `--nlab`, and cluster/subgraph background+border → reuse `--surface` +
    `--border` **only inside CSS contexts**:
    the SVG's `<style>` block and inline `style=` attributes.
  - Convert color-bearing **presentation attributes** (`fill="#…"`,
    `stroke="#…"`) into `style="fill:var(--…)"` — `var()` is invalid in SVG
    presentation attributes, valid in CSS/`style`.
  - Strip fixed `width`/`height`; keep `viewBox` so the SVG scales in
    `.diag-card`.
  - Add `role="img"` and inject `<title>`/`<desc>` (from Mermaid
    `accTitle`/`accDescr` if present, else a generated label) for a11y parity
    with the `obs-*` figures.
- Write `themes/scryops/assets/diagrams/<hash>.svg` (committed).

### Component 2 — Shortcode: `themes/scryops/layouts/shortcodes/mermaid.html`

Compute `sha256` of the trimmed `.Inner` (same normalization as the script),
then `resources.Get (printf "diagrams/%s.svg" $hash)`:

```html
<figure class="diagram">
  <div class="diag-card">{{ $svg.Content | safeHTML }}</div>
  <div class="mermaid">{{ .Inner }}</div>
</figure>
```

- SVG found → emit inline SVG in `.diag-card`, keep `.mermaid` source for Lite.
- SVG missing → `errorf` (fail the Hugo build) as defense-in-depth behind the CI
  guard, so no page ever ships a broken diagram.

### Component 3 — CSS: `themes/scryops/assets/css/telemetry.css`

- Default `.diagram .mermaid{display:none}` — the SVG is the render; the source
  is dormant.
- **Repoint the fallback**: move the "diagram source" text styling
  (currently at `html:not(.js) .diagram .mermaid` + `::before`) to
  **`html.pref-lite` only**. Under Lite, also hide the SVG
  (`html.pref-lite .diag-card > svg{display:none}`). No-JS now shows the SVG.
- No new tokens — the tokenized SVG resolves `--node-*`/`--edge`/`--nlab` from
  the cascade (`:root` / `html.light` / `html.calm`).

### Component 4 — CI guard: extend `scripts/verify_visuals.py` (existing `validate` job)

- For each `{{< mermaid >}}` block, recompute the hash and assert
  `themes/scryops/assets/diagrams/<hash>.svg` exists; fail with a clear
  "run `scripts/render-diagrams.py`" message if not.
- Warn/fail on orphan SVGs (committed files no diagram references).
- Zero new CI runtime — reuses the Python `validate` job.

### Component 5 — Removals (after SVG ships and is verified)

- Delete the Mermaid loader `<script>` block in `baseof.html` (~L160–182) and
  the `mermaid-init.js` resource reference.
- `git rm themes/scryops/assets/js/mermaid-init.js`
- `git rm themes/scryops/assets/js/vendor/mermaid.min.js` (3.2 MB).
- Colophon `content/colophon/_index.md:19` →
  `Mermaid · pre-rendered static SVG — 0 JS`.

## Hash contract (footgun — pin exactly)

The shortcode (Hugo), the render script (Python), and the CI guard (Python) must
compute an **identical** key or SVGs won't be found:

- Algorithm: **SHA-256**, hex, first **12** chars.
- Input: the shortcode's `.Inner` with **leading/trailing whitespace trimmed**
  (Hugo `trim`/`strings.TrimSpace`; Python `str.strip()`), no interior
  normalization.
- Hugo 0.145 exposes `sha256`; Python uses `hashlib.sha256`. Both must hash the
  **same trimmed byte string** (UTF-8).

## Error handling

- Missing SVG at build → shortcode `errorf` fails the Hugo build.
- Missing/stale SVG pre-build → CI `validate` job fails with remediation text.
- `mmdc` render failure for a diagram → script exits non-zero, names the source
  file and diagram, writes no partial SVG.

## Testing / verification

Build with **Hugo 0.145** (`~/bin/hugo`, matching CI — not 0.159 on PATH).
Preview `guides/slos-and-error-budgets` (7 diagrams):

1. SVG renders and inverts correctly across **dark / light / calm**.
2. Renders **with JS disabled** (the core win).
3. **Lite mode** shows the text source, hides the SVG.
4. The page's footprint badge drops from ~1 MB to KB.
5. Cache-bust `style.css` when checking CSS edits in-browser (the theme CSS is a
   single unfingerprinted file — known gotcha).

## Trade-offs accepted

- One **dev-only** Node dependency (`mmdc`) that never enters CI or the shipped
  bundle.
- Authors must run `scripts/render-diagrams.py` before pushing — enforced by the
  CI guard so a forgotten render fails loudly, not silently.

## Out of scope

- Rendering in CI (Chromium/Kroki) — rejected to keep the deploy lean.
- A dedicated `--diag-*` token set — reuse the shared `obs-*` tokens instead.
- Restyling the `obs-*` bespoke figures (they already use these tokens).
