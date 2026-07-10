# Design-system reconciliation — Phase 1: Tokens

**Date:** 2026-07-10
**Status:** Approved design — pending implementation plan
**Branch:** `feat/mermaid-static-svg` (building atop existing uncommitted a11y/polish WIP, per user)

## Context

The user imported the **ScryOps Design System** handoff bundle (claude.ai/design, `27fc099d-…`) and asked to reconcile the live Hugo theme to match it. The bundle's `tokens/colors.css` header states it was "Ported from telemetry.css, then **REFINED (Jul 2026)** toward the calm reading direction" — a deliberate, not-yet-shipped **warm / de-neon** palette revision. Two drift audits (tokens + components) confirmed the design system is the source of truth, with two documented exceptions where the theme is ahead (see Roadmap).

This spec covers **Phase 1 only: foundation tokens.** It is the highest-value, best-bounded slice — a single-file change to `telemetry.css` that, via the theme's bridge-alias block, cascades the new palette to every component automatically and re-themes all inline diagram SVGs for free.

Full reconciliation roadmap (each its own spec → plan → build): **Phase 1 Tokens (this doc)** → Phase 2 Component drift → Phase 3 New components/sections → Phase 4 Cleanup.

## Decisions (locked)

- **Design system = source of truth**, EXCEPT two spots where the theme is measurably better and must NOT regress (deferred to later phases, noted here so Phase 1 doesn't touch them): TagPill 44px touch target (keep over DS's 32px); the richer hero+rail Listing page (keep over DS's flat feed).
- **Class renames to DS BEM (`scry-*__*`) convention:** approved, but scoped to the component phases (2–3), NOT Phase 1. Phase 1 changes token *values* only, never token *names*.
- **`html.calm` is untouched** — the audit found it byte-identical to the design system already.
- **Building atop uncommitted WIP:** the working tree has an in-flight a11y/polish pass (aria-labels on `obs-*` shortcodes; `--bg`/`--lh-body` tweaks). Phase 1 supersedes the WIP's `--bg` and `--lh-body` token values with the design-system values; all other WIP edits (aria-labels, prefs.js, etc.) are left untouched.

## Scope of Phase 1

Edit **only** `themes/scryops/assets/css/telemetry.css`. Three changes:

### 1. Dark theme color block (`:root`)
Set every color token in the `:root` block to its **design-system value** from `tokens/colors.css` `:root`. Authoritative source (in the handoff bundle):
`…/scratchpad/ds-handoff/scryops-design-system/project/tokens/colors.css`.

The warm/de-neon shift spans the foundation colors and the derived figure/callout/table tokens. Headline changes (the plan enumerates all ~30 exactly):

| token | current | → design system |
|---|---|---|
| `--bg` | `#0F1617`* | `#141210` |
| `--surface` | `#151E1F` | `#1C1915` |
| `--border` | `#1E2C2E` | `#2B2620` |
| `--heading` | `#EAF0EE` | `#ECE6D9` |
| `--text` | `#D6DBD9` | `#D7D0C4` |
| `--muted` | `#7FA6A0` | `#9B9382` |
| `--green` | `#3DDC84` | `#66C892` |
| `--cyan` / `--link` | `#5BD8E8` | `#6FC6D1` |
| `--warn` | `#E0C24A` | `#DCC061` |
| `--danger` | `#FF6B6B` | `#F0857A` |
| `--violet` | `#9D7CF0` | `#A78FE0` |
| `--node-fill` | `#10191A` | `#16120C` |
| `--node-stroke` | `#2BAE76` | `#4FA77C` |
| `--edge` | `#5BD8E8` | `#6FC6D1` |
| `--nlab` | `#EAF0EE` | `#ECE6D9` |

Plus the derived tokens: `--ic-bg/-text/-bd`, `--fig-bg/-grid/-bd`, `--info-bg/-bd/-lb`, `--warn-bg/-lb`, `--dgr-bg/-bd/-lb`, `--th`, `--tborder` — all to their design-system values (enumerated in the plan).

*`--bg` current shows the uncommitted-WIP value `#0F1617`; the committed baseline is `#0A0E0F`. Either way the target is `#141210`.

**Do not change** in `:root`: the always-dark code-well tokens (`--code-bg/-text/-bd/-hi/-muted/-green/-cyan`) and `--eco`/`--eco-bright` — the audit confirmed these already match the design system and must stay constant across themes.

### 2. Light theme color block (`html.light`)
Set the drifted `html.light` color tokens to their design-system values (warm cream). ~14 tokens: `--bg #F6F3EC`, `--surface #FFFDF7`, `--border #E6DFD2`, `--heading #1E1811`, `--text #2C261E`, `--muted #6F6556`, `--ic-bg #EDE7DB`, `--ic-bd #DED6C7`, `--fig-bg #FFFDF7`, `--fig-grid` base `#EDE7DB`, `--fig-bd #E6DFD2`, `--node-fill #F0EBE0`, `--nlab #2C261E`, `--th #EFEAE0`, `--tborder #E6DFD2`. The light **accent** colors (`--green/--cyan/--link/--warn/--danger/--violet`, callout `--info/--warn/--dgr-*`, `--node-stroke`, `--edge`) already match — leave them.

### 3. Typography line-heights + radius tokens
- `--lh-body`: → `1.75` (supersedes WIP's `1.7`; committed baseline was `1.78`).
- `--lh-lede`: → `1.72`.
- Add two missing spacing tokens to `:root`: `--radius-retro:3px;` and `--radius-pill:999px;` (the design system defines both; the theme currently hardcodes `999px` inline and has no 3px radius). Adding them is additive — no rule needs to consume them in Phase 1; wiring existing `999px` literals to `var(--radius-pill)` is a Phase 2 component concern.

## Out of scope for Phase 1

- Any `html.calm` change (already matches).
- Token **name** changes / BEM renames (Phase 2–3).
- Component markup, Button states, Eyebrow tone, party-gallery hex→token, homepage sections, cleanup of dead files (`static/css/style.css`, `nav.html`) — later phases.
- The uncommitted WIP's non-token edits (aria-labels, prefs.js) — left as-is.

## Architecture / why this is safe & high-leverage

- **Single file, values-only.** No selectors, no markup, no JS. Token *names* are unchanged, so every existing rule keeps resolving.
- **Bridge aliases cascade.** `--accent:var(--green)`, `--ok:var(--green)`, `--info:var(--cyan)`, `--link`, etc. mean changing the base palette propagates to buttons, CTAs, tags, badges, links site-wide with no per-component edits.
- **Diagrams re-theme for free.** The 43 pre-rendered Mermaid SVGs and the `obs-*` figures read `var(--node-fill/--node-stroke/--edge/--nlab)`; changing those tokens recolors every diagram (dark + light) with zero re-render. Calm diagrams are unaffected (calm unchanged).

## Risk notes

- **Site-wide visual change (intended).** `--bg/--surface/--border/--heading/--text/--muted` are the highest-blast-radius tokens; this is the deliberate warm/de-neon refinement, applied globally in one edit.
- **Contrast (a11y).** The design system claims AA is preserved (dark body ~12.6:1). Verification must confirm body text and link contrast still meet AA in dark and light after the shift.
- **Line-height reflow.** `--lh-body` 1.7→1.75 slightly changes vertical rhythm across all body copy; low risk, purely cosmetic.
- **WIP overlap.** Only `--bg` and `--lh-body` collide with the uncommitted WIP; Phase 1 intentionally supersedes both. No other WIP file is touched.

## Verification

Build with **Hugo 0.145** (`~/bin/hugo`, CI version) — expect `0 errors`. Then, on a running preview (drafts on):
1. **Dark:** computed `--bg` = `rgb(20,18,16)` (`#141210`); a heading/link/diagram node reflects the new de-neoned green/cyan.
2. **Light:** computed `--bg` = `#F6F3EC`; accents unchanged; figure/table tokens warmed.
3. **Calm:** unchanged from before (regression check — same computed values as pre-Phase-1).
4. **Diagram recolor:** an `obs-*` figure and a pre-rendered Mermaid SVG show the new `--node-stroke/--edge/--nlab` in dark and light; calm unchanged.
5. **Contrast:** body text vs `--bg` and links vs `--bg` meet WCAG AA (≥4.5:1 normal text) in dark and light.
6. **Footprint:** unaffected (no bytes added beyond ~2 token lines).
7. Cache-bust the fingerprinted stylesheet as needed (Hugo Pipes fingerprints `telemetry.css`, so a rebuild changes its hash automatically).

## Success criteria

`telemetry.css` `:root` and `html.light` color blocks, the two line-heights, and the two new radius tokens equal the design-system values; `html.calm` and all non-token content unchanged; Hugo builds clean; dark/light visibly warm + de-neon; calm identical; diagrams recolored dark/light; AA contrast holds.
