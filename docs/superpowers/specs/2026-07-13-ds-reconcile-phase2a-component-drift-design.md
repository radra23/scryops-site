# DS reconciliation — Phase 2a: Component drift fixes

**Date:** 2026-07-13
**Status:** Approved design — pending implementation plan
**Branch:** `feat/mermaid-static-svg` (atop existing a11y WIP, per Phase 1)

## Context

Phase 1 (tokens) shipped the warm/de-neon palette (commit `c4c4206`). Phase 2 addresses component drift and was split (user decision) into **2a — localized visual/behavioral drift fixes (this doc)** and **2b — the cross-cutting BEM `scry-*__*` class rename**, done last as an isolated mechanical sweep. This keeps regressions bisectable: 2a changes appearance/behavior under the *current* class names; 2b only renames.

Source of truth: the ScryOps Design System bundle (`…/scratchpad/ds-handoff/scryops-design-system/project`). Five discrete fixes, each independently verifiable.

## Decisions (locked)

- **No class renames in 2a** — add states/rules under existing names (`.btn`, `.eyebrow`, `.party-*`, `.quote-*`, `.obs-table`). Renames are Phase 2b.
- **Eyebrow brand assignment:** default `.eyebrow` is muted; only the homepage hero eyebrow gets `.brand` (green). Section/list eyebrows stay muted.
- **party-gallery:** tokenize card *chrome* only; **keep** each character's accent hex (identity, not theme chrome).
- **obs-mascot / DS `scry-cucco` Mascot rebuild is OUT of 2a** — its sprite pixels are artwork and its per-class accents are identity; a DS-conformant Mascot (variants + LVL/HP/XP) is a Phase 3 component build, not a drift fix.
- Building atop the uncommitted a11y WIP: stage only the files this spec names; never `git add -A`.

## The five fixes

### 1. Eyebrow tone
**Files:** `themes/scryops/assets/css/telemetry.css:322,517`; `themes/scryops/layouts/_default/index.html` (hero eyebrow).
- There are **two conflicting `.eyebrow` rules** (line 322 and line 517), both `color:var(--green)`. Line 517 additionally carries `margin-bottom:11px` (used by section/list headers). Consolidate to a **single** base rule:
  `.eyebrow{font-family:var(--font-code);font-size:var(--fs-label);letter-spacing:.18em;text-transform:uppercase;color:var(--muted);display:inline-block}` plus `.eyebrow.brand{color:var(--green)}`. **Preserve the section-header spacing** that line 517's `margin-bottom:11px` provided — the plan must check line 517's call sites (e.g. `list.html`) and re-attach `margin-bottom` via the header context selector so header layout doesn't regress. Do not apply that margin globally (would shift the hero).
- Add `class="eyebrow brand"` to the homepage hero eyebrow only. Verify `list.html`/`qa` eyebrows remain plain `.eyebrow` (now muted).
- DS reference: `components/chrome/Eyebrow.jsx` — `.scry-eyebrow{color:var(--muted)} .scry-eyebrow.brand{color:var(--green)}`.

### 2. Button interaction states
**Files:** `themes/scryops/assets/css/telemetry.css:343-345`.
Extend the three `.btn*` rules to match `components/forms/Button.jsx` behavior (under current names): add `transition`, `:hover` (`.btn` border→`var(--cyan)`, color→`var(--heading)`; `.btn-primary` bg+border→`var(--cyan)`; `.btn-ghost` color→`var(--cyan)`), `:active{transform:translateY(1px)}`, `:focus-visible{outline:2px solid var(--link);outline-offset:2px}`, `[disabled],[aria-disabled="true"]{opacity:.45;cursor:not-allowed;pointer-events:none}`, and a `.btn.sm{font-size:12px;padding:7px 12px;min-height:34px}`. Add `min-height:40px` + `display:inline-flex;align-items:center;justify-content:center;gap:8px` to the base `.btn`. Replace the primary's hardcoded `color:#06120C` with `var(--on-accent)` (bridge alias = `var(--bg)`).

### 3. party-gallery chrome → tokens
**Files:** `themes/scryops/layouts/shortcodes/party-gallery.html` (inline `<style>` block).
Map hardcoded chrome hexes to tokens so cards adapt across dark/light/calm:
`#161616→var(--surface)`, `#0D0D0D→var(--bg)`, `#2A2A2A→var(--border)`, `#2E2E2E→var(--border)`, `#5A5A52→var(--muted)`, `#A8A8A0→var(--muted)`, `#F0EEE8→var(--text)`.
**Keep** the per-character `--ac`/accent hexes and the `.party-name` inline color (character identity). Only the neutral chrome changes.

### 4. QuoteWithAuthor avatar + initials
**Files:** `themes/scryops/layouts/shortcodes/quote_with_author.html`; `themes/scryops/assets/css/telemetry.css:639`.
- CSS: `.quote-avatar--pixel` width/height `64px→56px` (keep `border-radius:7px`).
- Shortcode initials: replace `{{ substr $author 0 2 | upper }}` with first-letter-of-each-of-first-two-words. Hugo: split `$author` on spaces, take `substr` first char of word[0] and word[1] (guarding single-word names → just word[0]'s first char), `upper`. Matches DS `QuoteWithAuthor` behavior ("Nostradamhen the Seer" → "NT"; single word "Cluckoo" → "C").

### 5. DataTable inline hex → tokens
**Files:** `themes/scryops/layouts/shortcodes/obs-comparison-table.html:3,46,47`.
Three inline hexes → semantic tokens: caption `color:#A8A8A0→var(--muted)`; v1 damage `color:#FF5555→var(--danger)`; v2 prevent `color:#30DD50→var(--green)`.

## Out of scope for 2a

- BEM class renames (Phase 2b).
- obs-mascot / DS Mascot rebuild, homepage sections, reusable partials (Phase 3).
- Dead-file cleanup (Phase 4).
- The uncommitted a11y WIP (leave unstaged).

## Verification

Build with **Hugo 0.145** (`~/bin/hugo`), 0 errors. On a throwaway preview server (own port), drive Playwright:
1. **Eyebrow:** homepage hero eyebrow computed `color` = `--green`; a section/list eyebrow computed `color` = `--muted`. Only ONE `.eyebrow` rule remains in the compiled CSS (no duplicate).
2. **Button:** a `.btn`'s `:hover` changes border to `--cyan` (check via forced `:hover` or computed state); `:focus-visible` shows an outline; `.btn.sm` renders smaller. (Confirm rules exist in compiled CSS + spot-check a CTA.)
3. **party-gallery:** on a page using `{{< party-gallery >}}`, a `.party-card` computed `background` = `--surface` in dark, and CHANGES to the light value when `html.light` is set (proves it now themes); character accent (`.party-name` color) unchanged across themes.
4. **QuoteWithAuthor:** pixel avatar computed width = `56px`; a two-word author renders two-letter initials from the two words.
5. **DataTable:** the two comparison cells compute to `--danger` / `--green`; caption to `--muted`; all shift correctly in light/calm.
6. Cross-theme sanity: nothing else visibly regressed; build clean.

## Success criteria

All five fixes land under current class names; eyebrows read muted except the branded hero; buttons have hover/active/focus/disabled/sm; party-gallery + DataTable theme correctly across dark/light/calm; pixel quote avatar is 56px with word-based initials; Hugo builds clean; the a11y WIP stays unstaged.
