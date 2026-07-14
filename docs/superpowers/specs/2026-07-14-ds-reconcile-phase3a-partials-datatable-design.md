# DS reconciliation — Phase 3a: Reusable partials + DataTable a11y

**Date:** 2026-07-14
**Status:** Approved design — pending implementation plan
**Branch:** `feat/mermaid-static-svg` (tree clean; Phases 1/2a/2b done)

## Context

Phase 3 (DS-conformant components) is decomposed into 3a (this doc — foundational, low-risk), 3b (structural + homepage UI), 3c (Mascot/cucco rebuild). Phase 3a delivers three contained, high-value pieces: extract two inline blocks into reusable Hugo partials (DRY) and bring the two DataTable shortcodes to consistent DS structure (a11y row-headers + scroll container).

Source of truth: DS components `eco/FootprintBadge.jsx`, `forms/SubscribeForm.jsx`, `data/DataTable.jsx` (scratchpad bundle).

## Decisions (locked)

- 3-sub-phase sequencing (3a foundational → 3b structural/homepage → 3c Mascot); user picked the full Phase-3 backlog.
- Partials keep the existing `.scry-*` classes and `data-*` hooks verbatim — `footprint.js` and the subscribe script are unchanged in behavior.
- DataTable: pure additive a11y/structure (row-header cells + scroll wrapper); the visual output is unchanged except a horizontal scrollbar appears only when the table overflows.
- Build/verify with Hugo 0.145. No AI commit attribution.

## Component 1 — FootprintBadge partial

**New:** `themes/scryops/layouts/partials/footprint-badge.html`
**Modify:** `themes/scryops/layouts/partials/footer.html` (call the partial).

Extract the footer's `.scry-fp` block (currently `footer.html:6-11`) into a partial that accepts a params dict:
- `budget` (bytes; default `122880`) → `data-fp-budget`.
- `methodHref` (default `/colophon/#method`).

The partial emits the identical markup — `data-footprint`, all `data-fp-*` attributes, and `.scry-fp*` classes verbatim — so `footprint.js` (which selects by `data-footprint`/`data-fp-*`) works unchanged. `footer.html` calls `{{ partial "footprint-badge.html" (dict "budget" 122880) }}`.

**Reuse:** the partial can now be dropped on the colophon page. Whether to *also* add it there is a plan step (optional), not required for 3a's success — but the point of the extraction is that reuse becomes possible.

**Constraint:** the badge markup has no `id`s, so multiple instances per page are safe.

## Component 2 — SubscribeForm partial

**New:** `themes/scryops/layouts/partials/subscribe-form.html`
**Modify:** `themes/scryops/layouts/_default/index.html` (call the partial in place of the inline block).

Extract the homepage's `{{ with .Site.Params.brevo_form_url }}…{{ end }}` block (`index.html:38-110`) — the `.scry-sub` section AND its inline `<script>` — into the partial. The partial reads `.Site.Params.brevo_form_url` itself (self-gating: renders nothing if unset) so any page can call `{{ partial "subscribe-form.html" . }}`. Behavior (4-state machine, no-cors Brevo POST, regex validation) is copied verbatim.

**Constraint (document in the partial + spec):** the form uses fixed `id`s (`subscribe-form`, `subscribe-email`, `subscribe-btn`, `subscribe-msg`) that the script drives via `getElementById`. So the partial is reusable on *different* pages but MUST NOT appear twice on the *same* page (duplicate ids would break the script). A future multi-instance need would require id-uniquifying; out of scope for 3a. The homepage keeps its single instance.

## Component 3 — DataTable a11y structure

**Modify:** `themes/scryops/layouts/shortcodes/obs-comparison-table.html`, `themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html`, `themes/scryops/assets/css/telemetry.css`.

Bring both tables to consistent DS `DataTable` structure:
1. **Row-header cells:** every row's first (label) cell is `<th scope="row" class="rowhead">`.
   - `obs-monitoring-shifts.html` already uses `<th scope="row">` — just add `class="rowhead"`.
   - `obs-comparison-table.html` currently uses plain `<td>` for row labels (e.g. `<td>Core question</td>`) — change each row's first `<td>` to `<th scope="row" class="rowhead">`.
2. **Scroll wrapper:** wrap each `<table class="scry-table">` in `<div class="scry-table-wrap">`.
   - `obs-comparison-table.html` has no wrapper — add one.
   - `obs-monitoring-shifts.html` wraps in a bare `<div style="overflow-x:auto">` — replace with `<div class="scry-table-wrap">`.
3. **CSS:** add `.scry-table-wrap{overflow-x:auto}`. Fold `.rowhead` into the existing row-header style selector so it's styled identically to the current `th[scope="row"]`/`td:first-child` rule (no visual change to row labels).

**No visual change** except: a horizontal scrollbar now appears on narrow viewports when a table overflows (an improvement), and comparison-table's row labels become semantically `<th scope="row">` (screen-reader row headers; they already looked like headers via the first-column style).

## Verification

Build with Hugo 0.145 (`0 errors`). On a preview:
1. **Footprint badge** still renders + fills in the footer (footprint.js via data-attrs); if the plan adds it to the colophon page, it renders there too.
2. **Subscribe form** renders from the partial on the homepage (when `brevo_form_url` is set), and its state machine still works (validation → loading → success/error); renders nothing when the param is unset.
3. **Tables:** both `scry-table`s are wrapped in `.scry-table-wrap` (horizontal scroll on narrow width); every row's first cell is `<th scope="row" class="rowhead">`; row-label styling visually unchanged; `aria-describedby`/caption intact.
4. Nothing else visibly regressed; partials produce byte-equivalent rendered output to the prior inline blocks (diff the built footer/homepage HTML — should match modulo whitespace).

## Out of scope for 3a

- 3b (Wordmark DOM, ReadingPrefs positioning, homepage post-grid, TopicRow, ModeToggle) and 3c (Mascot).
- Multi-instance-per-page SubscribeForm (id-uniquifying).
- Deleting the now-inline-free code beyond what the extraction requires; dead-CSS cleanup (Phase 4).

## Success criteria

Footprint badge and subscribe form are reusable partials (footer + homepage call them; behavior/markup unchanged; JS untouched); both DataTables share consistent `<th scope="row" class="rowhead">` + `.scry-table-wrap` structure with a `.scry-table-wrap{overflow-x:auto}` rule; Hugo builds clean; rendered output unchanged except the added a11y/scroll affordances.
