# Accessibility Audit: Cardinality Management (Guide)

**Page:** `http://localhost:1313/guides/cardinality-management/`
**Standard:** WCAG 2.1 AA | **Date:** 2026-06-15

**Method:** Static audit of the rendered source — `content/guides/cardinality-management.md`, the `_default/single.html` + `baseof.html` + partials chain, `themes/scryops/static/css/style.css`, the two page-specific SVG shortcodes (`obs-cardinality-explosion`, `obs-cardinality-meter`), and the Chroma/Monokai code styling from `hugo.toml`. Contrast ratios were computed by hand from hex values (WCAG relative-luminance formula). The draft page is not in `public/`, so the chrome was read from an identically-templated built guide. Not yet done (needs a live browser/AT pass): real keyboard tab-through, screen-reader announcement, and a visual 200%-zoom check.

---

## Summary

**Issues found: 8** | **Critical: 0** | **Major: 2** | **Minor: 6**

The page chrome is in good shape: it has a working skip link, correct landmarks (`nav[aria-label]`, `main`, `footer`), a clean single-`h1` → `h2` heading order, a visible high-contrast focus indicator, and thorough `role="img"` + `<title>`/`<desc>` text alternatives on both diagrams. Body text, links, headings, and UI labels all clear AA comfortably (8:1–17:1).

The two real failures both affect **low-vision sighted users**, not screen-reader users: syntax-highlighted code tokens and the small annotation text inside the cardinality-explosion diagram fall below 4.5:1.

---

## Findings

### Perceivable

| # | Issue | WCAG | Severity | Recommendation |
|---|-------|------|----------|----------------|
| 1 | Monokai code tokens fail contrast on the `#272822` code background: **keywords `#f92672` ≈ 3.9:1**, **comments `#75715e` ≈ 3.0:1**. This guide is code-heavy (C#, YAML, PromQL, Bash), so it affects core content. | 1.4.3 Contrast | 🟡 Major | Switch `[markup.highlight] style` from `monokai` to a higher-contrast dark theme and re-verify all tokens ≥ 4.5:1, or override the two offenders (e.g. keyword → `#ff6188` ≈ 5.2:1, comment → `#999990` ≈ 5.2:1). |
| 2 | Annotation text inside `obs-cardinality-explosion.svg` is too low-contrast: sub-labels `#805555` "user_id × status" ≈ 3.0:1, `#555550` "tier × channel × status" ≈ 2.5:1, caption `#1C7A2E` "manageable, predictable" ≈ 3.5:1, header `#CC4444` "UNBOUNDED LABELS" ≈ 4.0:1, and bottom notes / `ts` filler `#3A3A3A`/`#553333` ≈ 1.7:1. | 1.4.3 / 1.4.11 | 🟡 Major | Raise to the bright palette already used in the same figure: secondary text → `#A8A8A0` (≈7.9:1), red/green callouts → `#FF6060`/`#28CA41`. This matches the house diagram-contrast rule (labels bright, never muted grey). SR users are unaffected — the `<desc>` already describes it fully. |
| 3 | The intended reading face **iA Writer Quattro is not shipping** (`static/fonts/iawriter/*.woff2` is absent), so long-form body text falls back to Commit Mono (monospace). Contrast is fine; readability of a code-heavy long read is the concern. | 1.4.8 (AAA) / readability | 🟢 Minor | Ship the woff2 files, or accept mono and drop the dead `@font-face`. |
| 4 | Recurring **bold lead-in paragraphs** ("User IDs…", "Raw request IDs…", "Dynamic path segments…") read as sub-sections but are `<p><strong>`, not headings — so they're absent from the heading outline. | 1.3.1 Info & Relationships | 🟢 Minor | Optional: promote to `h3` for a richer outline and in-page navigation. |
| 5 | The `obs-cardinality-meter` "SERIES vs CEILING" label is an **8px Press Start 2P** pixel font. It passes contrast (`#808080` ≈ 4.9:1) but is very small. | 1.4.4 (readability) | 🟢 Minor | Bump to ≥ 10px for the pixel face. |

### Operable

| # | Issue | WCAG | Severity | Recommendation |
|---|-------|------|----------|----------------|
| 6 | Nav links are **44px tall but narrow** — short labels ("Q&A", "About") fall under 44px wide. Meets the 24px AA minimum (2.5.8) but not the 44px enhanced target. | 2.5.5 Target Size (AAA) | 🟢 Minor | Add horizontal padding or `min-width` so each hit area reaches 44×44. |
| 7 | Footer links ("about · q&a · tags") are inline text at ~22px line height — just under the 24px minimum target. | 2.5.8 Target Size (Min) | 🟢 Minor | Add `padding`/`line-height` to give footer links ≥ 24px height. |

### Understandable

No issues. `html[lang="en"]`, consistent navigation, predictable behavior, and no forms or inputs on this page.

### Robust

| # | Issue | WCAG | Severity | Recommendation |
|---|-------|------|----------|----------------|
| 8 | Code blocks render as Hugo/Chroma `<pre tabindex="0">` — keyboard-focusable for horizontal scroll, which is correct, but the focusable scroll region has no accessible name. | 4.1.2 (minor) | 🟢 Minor | Optional: add `role="region"` + `aria-label="code sample"` to long scrollable blocks. Landmarks, SVG `role="img"` names, and `aria-hidden` on decorative art are all correct. |

---

## Color Contrast Check

| Element | Foreground | Background | Ratio | Required | Pass? |
|---------|-----------|------------|-------|----------|-------|
| Body / prose text | `#F0EEE8` | `#0D0D0D` | 16.8:1 | 4.5:1 | ✅ |
| Excerpt | `#C8C6C0` | `#0D0D0D` | 11.4:1 | 4.5:1 | ✅ |
| Muted (read-time, figcaption, footer, nav) | `#A8A8A0` | `#0D0D0D` | 8.1:1 | 4.5:1 | ✅ |
| Prose links / h2 | `#F5A623` | `#0D0D0D` | 9.6:1 | 4.5:1 | ✅ |
| "Guide" tag | `#4D9FFF` | `#0D0D0D` | 7.1:1 | 4.5:1 | ✅ |
| Focus outline | `#F5A623` | `#0D0D0D` | 9.6:1 | 3:1 | ✅ |
| Diagram primary labels (service/endpoint) | `#F0EEE8` | `#0A0B0E` | 17.0:1 | 4.5:1 | ✅ |
| Diagram key numbers (12 / 100,000 series) | `#28CA41` / `#FF6060` | `#111111` | 8.7:1 / 6.4:1 | 4.5:1 | ✅ |
| **Code keywords** | `#f92672` | `#272822` | **3.9:1** | 4.5:1 | ❌ |
| **Code comments** | `#75715e` | `#272822` | **3.0:1** | 4.5:1 | ❌ |
| **Diagram sub-label "user_id × status"** | `#805555` | `#111111` | **3.0:1** | 4.5:1 | ❌ |
| **Diagram caption "manageable, predictable"** | `#1C7A2E` | `#111111` | **3.5:1** | 4.5:1 | ❌ |
| **Diagram header "UNBOUNDED LABELS"** | `#CC4444` | `#111111` | **4.0:1** | 4.5:1 | ❌ |
| **Diagram notes / `ts` filler** | `#3A3A3A`/`#553333` | `#0D0D0D`/`#111111` | **~1.7:1** | 4.5:1 | ❌ |

## Keyboard Navigation

| Element | Tab order | Enter/Space | Focus visible | Notes |
|---------|-----------|-------------|---------------|-------|
| Skip link | First | Jumps to `#main-content` | ✅ slides into view | Correct |
| Nav links | DOM order, logical | Activates | ✅ amber outline | 44px tall |
| Tag-pills / in-prose links | After nav | Activates | ✅ | Standard `<a>` |
| Code blocks | In flow | n/a | ✅ (`tabindex=0`) | Scrollable via keyboard |
| Footer links | Last | Activates | ✅ | — |

No custom JS widgets render on this page (the terminal-toggle and feed-filter scripts no-op here), so there are no focus traps, no keyboard-only gaps, and no auto-playing motion (the pixel-chicken easter egg is commented out in `baseof.html`).

## Screen Reader

| Element | Announced as | Issue |
|---------|--------------|-------|
| Page | "scryops", lang en, `<main>` | None |
| Nav | "Primary, navigation" | None — `aria-label="Primary"` |
| Heading outline | h1 title → six h2 | None (bold lead-ins absent — see #4) |
| Both diagrams | `img`, full `<title>` + `<desc>` | None — exemplary text alternatives |
| Insight icon / mascot art | (skipped) | Correct — `aria-hidden` / `aria-label` |
| Mascot figure | "Conan the Bawkbarian, a pixel-art barbarian-class chicken, says: …" | None — quip exposed via `aria-label` |

---

## Priority Fixes

1. **Raise code-token contrast (Finding 1, Major)** — change the Chroma `style` or override keyword/comment colors to clear 4.5:1. Highest impact: code is the core of this guide and the failure is site-wide.
2. **Brighten the cardinality-explosion diagram labels (Finding 2, Major)** — reuse the bright palette already in the figure. Restores the page's flagship visual for low-vision readers and matches the house diagram-contrast standard.
3. **Polish (Findings 3–8, Minor)** — ship the reading font, enlarge nav/footer touch targets, and optionally promote bold lead-ins to `h3`.

---

## Fixes Applied & Corrections — 2026-06-15

| # | Finding | Status | What changed |
|---|---------|--------|--------------|
| 1 | Code-token contrast | ✅ Fixed | `hugo.toml` → `noClasses = false`; added a class-based Chroma palette to `style.css` tuned to the `#161616` code surface (keywords `#FF6188` ~6.3:1, comments `#A6A28C` ~7:1, strings/types/numbers 6–13:1). Any unstyled token inherits the bright base, so it can't fail. |
| 2 | Diagram-label contrast | ✅ Fixed | `obs-cardinality-explosion`: headers, sub-labels, captions and notes raised to `#A8A8A0` / `#28CA41` / `#FF6060` (≈6–8:1). Decorative `ts` grid texture left intentionally faint (it carries no information; the `<desc>` covers meaning). |
| 3 | Body reading font "not shipping" | ⚠️ Retracted — not an issue | **False positive.** The `iA Writer Quattro` woff2 files *do* exist at `themes/scryops/static/fonts/iawriter/` and are correctly wired via `@font-face` + `--font-sans`; body already renders in Quattro. My original check was misled by a Glob tool false-negative. No change needed — the temporary fallback edit was reverted. |
| 4 | Bold lead-ins not headings | ◻︎ Left by choice | These are inline sentence subjects ("**User IDs…** are the canonical examples"); promoting to `h3` means rewriting the author's published prose. Flagged for an editorial decision rather than changed silently. |
| 5 | Meter 8px pixel label | ➖ Superseded | `obs-cardinality-meter` was redesigned since the audit (now a "Series Budget / Query Cost Cliff" gauge). The old label is gone; its real issue — section headers `#CD384B` at ≈3.9:1 — was fixed (`#CD384B` → `#E85A6E`, ≈5.7:1). |
| 6 | Nav touch targets | ✅ Fixed | `.nav-links a` now 44×44 (min-width + centered + wider padding). |
| 7 | Footer touch targets | ✅ Fixed | `footer a` now ≥24px (inline-block, min-height 24px, padding). |
| 8 | Unnamed scrollable code | ✅ Fixed | Progressive-enhancement script in `baseof.html` labels overflowing code as `role="region"` + descriptive `aria-label`. |

**Verification:** CSS braces balanced (296/296), inline JS passes `node --check`, `hugo.toml` highlight block confirmed, Chroma palette + a11y script present, diagram source greps clean of the old low-contrast hexes. A full `hugo` build was **not** run (Hugo isn't installed in this sandbox) — run `hugo server` and eyeball the diagrams + code blocks to confirm.
