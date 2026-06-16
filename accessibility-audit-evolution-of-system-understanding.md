# Accessibility Audit: The Evolution of System Understanding (Article)

**Page:** `http://localhost:1313/articles/evolution-of-system-understanding/`
**Standard:** WCAG 2.1 AA | **Date:** 2026-06-15

**Method:** Static audit of the rendered source — `content/articles/evolution-of-system-understanding.md`, the shared `single.html`/`baseof.html` chrome, `style.css`, and the three diagram shortcodes the article uses (`obs-knowledge-tiers`, `obs-monitoring-shifts`, `mermaid`). Contrast ratios computed by hand. The page-level chrome (skip link, landmarks, focus, headings, nav/footer touch targets) was audited and fixed earlier this session, so this pass focuses on the article's own content and visuals. Not done here (needs a live browser/AT pass): screen-reader announcement of the rendered Mermaid SVG and a 200%-zoom check.

---

## Summary

**Issues found: 5** | **Critical: 0** | **Major: 1** | **Minor: 4**

Strong page overall. The two `obs-*` figures are exemplary — full `aria-label` descriptions, visible `figcaption`s, semantic tables, and every label clearing AA (5.6:1–16.8:1). The article's headings nest cleanly (h1 → six h2). The one real gap: the **Mermaid flowchart ships with no text alternative**, unlike every other diagram on the site. The JSON code blocks, which would have failed before, now pass thanks to the class-based Chroma palette added earlier today.

---

## Findings

### Perceivable

| # | Issue | WCAG | Severity | Recommendation |
|---|-------|------|----------|----------------|
| 1 | The **Mermaid flowchart** (telemetry-evolution timeline) has no text alternative. `mermaid.html` wraps `{{ .Inner }}` in a bare `figure > .diag-card` with no `figcaption`, no `aria-label`, and the source has no `accTitle`/`accDescr`, so the rendered SVG exposes no accessible name or description — only loose node text. Every other diagram on the site provides a full description; this is the lone exception. | 1.1.1 Non-text Content | 🟡 Major | Add `accTitle:`/`accDescr:` lines to the flowchart source (Mermaid renders them into `<title>`/`<desc>`), and/or extend the `mermaid` shortcode to emit a `figcaption`. Mitigated in practice because the surrounding prose already narrates the same timeline. |
| 2 | **Mermaid node borders** are near-invisible: node fill `#1C1C1C` and border `#3A3A3A` on the `#161616` card ≈ 1.6:1, so the boxes barely separate from the background. Node *text* is bright and fine; only the container outline is weak. | 1.4.11 Non-text Contrast | 🟢 Minor | Raise `nodeBorder`/`primaryBorderColor` in the Mermaid theme (e.g. to `#5B8DEF` or `#6A6A6A`) for ≥3:1 box edges. |
| 3 | The `.knt-ls`/`.knt-tag` pixel labels in the knowledge-tiers figure are **~7.7px Press Start 2P** (`.48rem`). They pass contrast (4.9:1+) but are very small. | 1.4.4 (readability) | 🟢 Minor | Nudge the pixel labels up a step, or letter-space less aggressively. |

### Operable

No issues specific to this article. All interactive elements are native links (nav, tag-pills, footer) with the visible amber focus ring; nav/footer target sizes were corrected earlier today. The wide tables/code use `overflow-x:auto` and reflow on mobile.

### Understandable

| # | Issue | WCAG | Severity | Recommendation |
|---|-------|------|----------|----------------|
| 4 | Recurring **bold lead-ins** ("**Known-knowns**…", "**Reactive to proactive.**", "**Continuous profiling**…" — nine in total) read as sub-sections but are `<p><strong>`, so they're absent from the heading outline. Same pattern just restructured in the cardinality guide. | 1.3.1 Info & Relationships | 🟢 Minor | Optional: promote to `h3` (voice-preserving rephrase), matching the cardinality fix. |

### Robust

| # | Issue | WCAG | Severity | Recommendation |
|---|-------|------|----------|----------------|
| 5 | In `obs-monitoring-shifts`, the first-column cells ("When it acts", "What it sees", "Questions it answers") are **row headers marked as `<td>`**, not `<th scope="row">`. Column headers already use `<th scope="col">` correctly. | 1.3.1 / 4.1.2 | 🟢 Minor | Change the first `<td>` in each body row to `<th scope="row">` so screen readers announce the row dimension with each cell. |

---

## Color Contrast Check

| Element | Foreground | Background | Ratio | Required | Pass? |
|---------|-----------|------------|-------|----------|-------|
| Body / prose text | `#F0EEE8` | `#0D0D0D` | 16.8:1 | 4.5:1 | ✅ |
| Knowledge-tiers header | `#A8A8A0` | `#161616` | 7.6:1 | 4.5:1 | ✅ |
| Tier label — Known-Knowns | `#28CA41` | `#0D0D0D` | 8.9:1 | 4.5:1 | ✅ |
| Tier label — Unknown-Unknowns | `#FF6060` | `#0D0D0D` | 6.6:1 | 4.5:1 | ✅ |
| Tier sub-label (`.knt-ls`, ~7.7px) | `#808080` | `#0D0D0D` | 4.9:1 | 4.5:1 | ✅ (tiny) |
| Tier description | `#D8D6CE` | `#0D0D0D` | 13.4:1 | 4.5:1 | ✅ |
| Table — "Observable System" header | `#5B8DEF` | `#0D0D0D` | 6.0:1 | 4.5:1 | ✅ |
| Table — v2 cells | `#5B8DEF` | `#161616` | 5.6:1 | 4.5:1 | ✅ |
| Table — v1 cells | `#F0EEE8` | `#161616` | 15.6:1 | 4.5:1 | ✅ |
| Mermaid node text | `#F0EEE8` | `#1C1C1C` | 14.7:1 | 4.5:1 | ✅ |
| Mermaid connector lines | `#5B8DEF` | `#161616` | 5.6:1 | 3:1 (graphic) | ✅ |
| **Mermaid node border** | `#3A3A3A` | `#161616` | **1.6:1** | 3:1 (graphic) | ❌ |
| JSON code — keys/strings/numbers (post-fix) | `#66D9EF`/`#E6DB74`/`#AE81FF` | `#161616` | 6.4–12.7:1 | 4.5:1 | ✅ |

## Keyboard Navigation

| Element | Tab order | Activate | Focus visible | Notes |
|---------|-----------|----------|---------------|-------|
| Skip link → nav → tag links | Logical | Enter | ✅ amber ring | Shared chrome, verified earlier |
| JSON code blocks | In flow | n/a | ✅ (`tabindex=0`) | Now labelled as a region by the a11y script added today |
| Footer links | Last | Enter | ✅ | ≥24px targets (fixed today) |

No custom widgets, modals, focus traps, or auto-playing motion on this page.

## Screen Reader

| Element | Announced as | Issue |
|---------|--------------|-------|
| Headings | h1 title → six h2 | Clean outline; bold lead-ins absent (Finding 4) |
| `obs-knowledge-tiers` | "figure", full `aria-label` + readable text + caption | None — exemplary |
| `obs-monitoring-shifts` | "figure" + `aria-label`; table with column headers | Row dimension not tied to cells (Finding 5) |
| **Mermaid flowchart** | SVG with no name/description — loose node text only | **No text alternative (Finding 1)** |

---

## Priority Fixes

1. **Give the Mermaid diagram a text alternative (Finding 1, Major)** — add `accTitle`/`accDescr` to the flowchart (or a `figcaption` in the shortcode). Closes the one real gap and is the only place the site falls short of its own diagram standard.
2. **Polish (Findings 2–5, Minor)** — brighten Mermaid node borders, mark table row headers with `scope="row"`, optionally promote the bold lead-ins to `h3`, and nudge up the tiny pixel labels.

---

## Fixes Applied — 2026-06-15

| # | Finding | Status | What changed |
|---|---------|--------|--------------|
| 1 | Mermaid text alternative | ✅ Fixed (site-wide) | `mermaid.html` now accepts optional `alt` (→ `role="img"` + `aria-label` on the diagram) and `caption` (→ visible `figcaption`). Both degrade gracefully, so existing param-less diagrams render exactly as before. This article's flowchart now passes a full timeline `alt` + a caption. |
| 2 | Mermaid node borders | ✅ Fixed (site-wide) | `nodeBorder` / `primaryBorderColor` in the baseof Mermaid theme: `#3A3A3A` → `#6A6A6A` (~3.5:1 box edges, clears the 3:1 graphics threshold). |
| 3 | Tiny pixel labels | ✅ Fixed | `.knt-ls` / `.knt-tag` bumped `.48rem` → `.52rem`. |
| 4 | Bold lead-ins not headings | ✅ Fixed | All nine promoted to `h3` with voice-preserving rephrasing; clean h2→h3 nesting across the three sections. |
| 5 | Table row headers | ✅ Fixed (site-wide) | `obs-monitoring-shifts` first-column cells are now `<th scope="row">`; `style.css` mirrors the previous styling so the visual is unchanged. |

**Verification:** CSS braces balanced (296/296), inline JS passes `node --check`, and greps confirm the Mermaid borders (`#6A6A6A`), shortcode `aria-label`, 3× `th scope="row"` + 3× `th scope="col"`, 9× `h3`, and the article `alt`. The article was re-read for clean nesting and natural prose. A full `hugo` build was **not** run (Hugo isn't installed in this sandbox) — run `hugo server` to confirm the Mermaid `aria-label`/caption and the recolored borders render as expected.
