# DS reconciliation — Phase 2b: BEM class rename

**Date:** 2026-07-13
**Status:** Approved design — pending implementation plan
**Branch:** `feat/mermaid-static-svg` (working tree now CLEAN — the a11y + font WIP was committed as `1b9de59` + `c4f6383` before this phase)

## Context

Phase 1 (tokens) and Phase 2a (component drift) shipped. Phase 2b is the second half of Phase 2: rename the theme's DS-covered component class names to the design system's `scry-*__*` BEM convention (user-approved). It is a **purely mechanical, zero-visual-change** sweep, isolated from 2a so any rendering regression is bisectable to the rename alone.

Source of truth: DS component class inventory at `…/scratchpad/ds-handoff/scryops-design-system/project/components/`. The full `scry-*` inventory (~100 names) was extracted and is the naming target.

## Decisions (locked)

- **Full rename** — all ~17 DS-covered components.
- **DS names verbatim.** Adopt the DS `scry-<block>` / `scry-<block>__<element>` names exactly. Where a theme sub-element has no exact DS counterpart, coin a `scry-<block>__<element>` name in the same BEM family (documented in the plan's mapping) so each block is internally consistent.
- **Scope boundary — DS-covered components only.** Theme-only classes stay on legacy names: obs-* figure internals (`.node/.edge/.nlab/.arr/.obs-fig` etc.), layout classes (`.lst-*`, `.front-*`, `.layout`, `.article`, `.prose`, TOC), chroma/syntax classes, footprint-badge JS hooks that must match `footprint.js`, and reading-prefs `data-pref-*` attributes (attributes, not classes — untouched). **End-state is a deliberately mixed codebase.**
- **No behavior/value changes** — this phase renames selectors + emitted class attributes only. (Token values, states, markup structure are already done in 1/2a.)
- Build/verify with Hugo 0.145.

## Architecture — per-component rename, grouped into ~7 tasks

For each component: rename its theme classes → DS `scry-*` in `telemetry.css` (rule selectors) AND every template that emits them (partials/shortcodes/layouts). Grouped by area:

1. **forms** — `.btn/.btn-primary/.btn-ghost/.btn.sm` → `.scry-btn(.primary/.ghost/.sm)`; subscribe-form classes → `scry-sub__*`.
2. **content** — `.callout(.info/.warn/.danger)`+label → `scry-callout(__label)`; `.insight` → `scry-insight(__icon/__body)`; `.tag` → `scry-tag`; `.tag-pill` → `scry-tagpill`; `.quote-with-author`/`.quote-*` → `scry-quote(__body/__attr/__avatar/__initials/__name/__role)`.
3. **cards** — `.art-card/.art-num/.art-title/.art-*` → `scry-artcard__*`; `.post-card` → `scry-postcard__*`; `.topic-row/.topic-name/.topic-badge` → `scry-topicrow__*`.
4. **brand** — `.wordmark/.foot-logo` → `scry-wordmark(__mark/__tag)`; terminal feed `.feedwin/.trow/.tt/.tm/.tg2/.tp-*` → `scry-feed__*`; party/mascot `.party-*` + `obs-mascot` classes → `scry-cucco__*`.
5. **eco** — `.colophon/.co-cmd/.co-row/.co-k/.co-v` → `scry-colophon__*`; `.footprint/.fp-*` → `scry-fp__*` (keep `footprint.js` selectors in sync — JS hook update is part of this task).
6. **reading** — `.pref-*` panel classes → `scry-prefs__*` (NOT the `html.pref-*` theme-state classes, which are token overrides — leave those); mode-toggle segment → `scry-prefs__seg` / `scry-modetoggle` per DS. Keep `prefs.js` `data-pref-*` attribute hooks unchanged.
7. **data** — `.obs-table/.v1/.v2` (comparison + monitoring-shifts shortcodes) → `scry-table` (+ element classes per DS).

Each group is one task with an independently verifiable deliverable.

## Critical nuances

- **JS-coupled classes:** `footprint.js` selects `.footprint`/`.fp-*`; `prefs.js` uses `data-pref-*` **attributes** (not the panel classes). The eco task MUST update `footprint.js` selectors together with the CSS/markup rename. The reading task must NOT touch `data-pref-*` attributes or the `html.pref-*`/`.light`/`.calm` state classes (those are behavior, not component chrome).
- **`html.pref-*` vs `.pref-*`:** `html.pref-legible/spacing/reduce/lite` are theme-STATE classes (token overrides) — leave them. Only the reading-prefs PANEL component classes (the gear/dialog/segment UI) rename.
- **Shared/ambiguous classes:** if a theme class is used by BOTH a DS component and non-DS markup, renaming could break the non-DS use. Each task must grep all call sites first and confirm the class is component-exclusive before renaming; if shared, flag it (don't blindly rename).
- **`obs-mascot` vs party-gallery:** both map to `scry-cucco`; their pixel-art SVG fills and per-character accents are untouched (only the wrapper/card/stat chrome classes rename).

## Verification (per task — the whole safety story)

1. **No old class remains:** grep the renamed theme classes across `themes/scryops/{assets/css,layouts,assets/js}` → zero occurrences.
2. **No orphan new class:** every `scry-*` class emitted in a template has a matching CSS rule (and vice versa) — grep both directions.
3. **Build:** Hugo 0.145 `0 errors`.
4. **Rendered-identical:** on a preview, the component's key computed styles (color/background/font/size) are unchanged from before the rename; the visual output is identical (only the DOM `class` attribute strings differ).

Final task: full-site pass — load home + a reading page + meet-the-party + a diagram page in dark/light/calm; confirm nothing visually regressed and no unstyled (orphaned-class) elements.

## Out of scope

- Any visual/behavioral change (Phases 1/2a done); new components (Phase 3); dead-file cleanup (Phase 4).
- Theme-only classes (obs figures, layout, chroma), `html.pref-*` state classes, `data-pref-*` attributes.

## Success criteria

All ~17 DS-covered components use the DS `scry-*__*` class names in CSS + templates (+ `footprint.js` hooks); no old component class name remains and no orphaned new class exists; Hugo builds clean; every component renders pixel-identical across dark/light/calm; theme-only classes and JS behavior hooks untouched.
