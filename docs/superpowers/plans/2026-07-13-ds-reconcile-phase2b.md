# DS Reconciliation Phase 2b — BEM Class Rename · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the theme's DS-covered component classes to the design system's `scry-*__*` BEM names — a pure, zero-visual-change sweep — keeping current DOM, positioning, and behavior.

**Architecture:** Per-component-group tasks. Each renames class names in `telemetry.css` selectors + every emitting template + any JS that selects by class, then verifies no old class remains, no orphan new class exists, the build is clean, and the component renders pixel-identical. NO structural/DOM/positioning/new-CSS changes.

**Tech Stack:** Hugo 0.145 (extended), CSS custom properties, Hugo templates, a little vanilla JS.

## Scope refinement vs the spec (IMPORTANT — deviation from spec's literal "all 17")

The class-mapping research showed several DS components differ **structurally** from the theme (not pure renames) and three targets are **dead CSS**. To keep 2b a true zero-visual-change rename, this plan:
- **Pure-renames (in scope):** Button, SubscribeForm, Callout, Insight, Tag, TagPill, QuoteWithAuthor, ArticleCard, TerminalFeed, Colophon, FootprintBadge, ReadingPrefs-panel (name-only, keep `position:fixed`), Wordmark (name-only, keep flat DOM), DataTable (block class only, keep structure).
- **Deferred to Phase 3 (structural rebuilds, NOT renames):** Mascot/cucco (obs-mascot has no CSS + party-gallery merge), Wordmark nested `__mark`/`__tag` DOM, ReadingPrefs `.scry-prefs` wrapper + absolute positioning, DataTable `.rowhead`/`.scry-table-wrap`.
- **Skipped (dead CSS, no live markup) → Phase 4 cleanup:** `.post-card*`, `.topic-row/.topic-list/.topic-all`, `.mode-toggle`.

## Global Constraints

- **Build/verify with `~/bin/hugo` (0.145)**, not the 0.159 on PATH.
- **Pure rename only** — class-name text changes in CSS selectors + emitted `class="…"` + class-based JS selectors. NO DOM restructure, NO positioning change, NO new CSS rules, NO token/value change.
- **DO NOT rename STATE classes / attributes:** `html.pref-legible/spacing/reduce/lite`, `html.light`, `html.calm` (token-override state, set by `prefs.js` via `classList.toggle('pref-'+flag)` and read by the FOUC guard in `head.html`), and `data-pref-*` **attributes**. A prefix-style replace (`s/pref-/…/`) is FORBIDDEN — rename only exact panel class names.
- **Keep bare variant/atom classes** the DS keeps bare: tag variants `guide/howto/qa/trends`, feed `.fp`/`.fa`, table `.v1`/`.v2` (only the parent block renames).
- **JS coupling to update in lockstep** (class-based selectors only): `baseof.html` inline filter script (`.art-card`, `.tag`), `prefs.js:62-63` (`.pref-panel`, `.pref-btn`), `index.html:64` subscribe-msg class string. `footprint.js` needs **no change** (it selects by `data-*` attributes; `.over` modifier is unaffected).
- **Colophon lives in content**, not the theme: `content/colophon/_index.md`.
- **Stage only each task's named files.** No AI commit attribution.
- **Authoritative mapping:** the two research reports in this session (forms/content/data; cards/brand/eco/reading). Class targets below are copied from them.

---

## Task 1: forms — Button + SubscribeForm

**Files:** `themes/scryops/assets/css/telemetry.css`; `themes/scryops/layouts/_default/index.html` (hero CTAs + inline subscribe form/script).

**Mapping (exact):**
- `.btn`→`.scry-btn`; `.btn-primary`→(modifier) `.primary`; `.btn-ghost`→`.ghost`; `.btn.sm`→`.scry-btn.sm`. Markup: `class="btn btn-primary"`→`class="scry-btn primary"`, `class="btn btn-ghost"`→`class="scry-btn ghost"` (index.html:15-16). Also `.landing-cta .btn` (telemetry.css:664)→`.landing-cta .scry-btn`.
- `.subscribe-section`→`.scry-sub`; `.subscribe-label`→`.scry-sub__label`; `.subscribe-desc`→`.scry-sub__desc`; `.subscribe-form`→`.scry-sub__form`; `.subscribe-input`→`.scry-sub__input`; `.subscribe-btn`→`.scry-sub__btn`; `.subscribe-msg`→`.scry-sub__msg`; `.subscribe-msg--success/--error/--loading`→ plain modifiers `.success/.error/.loading` on `.scry-sub__msg`.
- **JS string (index.html:64):** `msg.className = 'subscribe-msg subscribe-msg--' + state;` → `msg.className = 'scry-sub__msg ' + state;` (state is `success`/`error`/`loading`).
- Leave the `id=` hooks (`subscribe-form`/`subscribe-email`/`subscribe-btn`) unchanged (JS uses ids).

- [ ] **Step 1: Rename in CSS + index.html + the JS string** (apply the mapping above).
- [ ] **Step 2: No-orphan verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rnE '\.(btn|btn-primary|btn-ghost|subscribe-section|subscribe-label|subscribe-desc|subscribe-form|subscribe-input|subscribe-btn|subscribe-msg)\b' themes/scryops/assets/css/telemetry.css themes/scryops/layouts/_default/index.html && echo "STALE remains" || echo "clean: no old form classes"
grep -n 'subscribe-msg--' themes/scryops/layouts/_default/index.html && echo "STALE js string" || echo "clean: js string updated"
grep -n 'class="scry-btn primary"' themes/scryops/layouts/_default/index.html && echo "btn markup OK"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b1 2>&1 | tail -3
```
Expected: `clean: no old form classes`, `clean: js string updated`, `btn markup OK`, `0 errors`.
- [ ] **Step 3: Commit** — `git add themes/scryops/assets/css/telemetry.css themes/scryops/layouts/_default/index.html` → `feat(ds-2b): rename forms (btn, subscribe) to scry-* BEM`.

---

## Task 2: content — Callout, Insight, Tag(+JS), TagPill, Quote

**Files:** `telemetry.css`; shortcodes `callout.html`, `insight.html`, `quote_with_author.html`; `layouts/_default/single.html`, `layouts/qa/single.html`, `layouts/partials/article-card.html`, `layouts/_default/list.html`, `layouts/_default/taxonomy.html`; `layouts/_default/baseof.html` (JS).

**Mapping (exact):**
- `.callout`→`.scry-callout` (keep `.info/.warn/.danger` modifiers); `.callout-label`→`.scry-callout__label`. (callout.html:13-14)
- `.insight`→`.scry-insight` (keep `.lightbulb/.bookmark`); `.insight-icon`→`.scry-insight__icon`; `.insight-body`→`.scry-insight__body`. (insight.html:2-15)
- `.tag`→`.scry-tag` **everywhere** (single.html:8-11, qa/single.html:8, article-card.html:9-12, list.html:39). **Keep variant classes bare** (`guide/howto/qa/trends/article`). **JS (baseof.html:151-152):** update `querySelector('.tag')`→`querySelector('.scry-tag')`; leave the `classList.contains(type)` variant check as-is.
- `.tag-pill`→`.scry-tagpill` (single.html:15, qa/single.html:10, taxonomy.html:9).
- `.quote-with-author`→`.scry-quote`; `.quote-attribution`→`.scry-quote__attr`; `.quote-avatar`→`.scry-quote__avatar`; `.quote-avatar--pixel`→ modifier `.pixel` (emit `class="scry-quote__avatar pixel"`); `.quote-avatar-initials`→`.scry-quote__initials`; `.quote-meta`→`.scry-quote__meta`; `.quote-name`→`.scry-quote__name`; `.quote-role`→`.scry-quote__role`. (quote_with_author.html:5-17)

- [ ] **Step 1: Apply the content mapping** across the CSS + all listed templates + the baseof.html JS selector.
- [ ] **Step 2: No-orphan verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rnE '\b(callout|callout-label|insight|insight-icon|insight-body|tag-pill|quote-with-author|quote-attribution|quote-avatar|quote-avatar-initials|quote-meta|quote-name|quote-role)\b' themes/scryops/assets/css/telemetry.css themes/scryops/layouts && echo "REVIEW matches (ensure none are the OLD class in class=/selector context)" || true
grep -rn "querySelector('.tag')" themes/scryops/layouts/_default/baseof.html && echo "STALE tag JS" || echo "clean: tag JS updated"
grep -rn 'class="tag' themes/scryops/layouts && echo "STALE bare .tag markup" || echo "clean: .tag markup renamed"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b2 2>&1 | tail -3
```
Expected: tag JS updated, no stale `class="tag"`/`class="tag ...`, build `0 errors`. (For the first grep, manually confirm any remaining hits are unrelated substrings — e.g. `data-tag`, `tags`, comments — not the renamed classes.)
- [ ] **Step 3: Commit** — the listed files → `feat(ds-2b): rename content components (callout/insight/tag/tagpill/quote) to scry-*`.

---

## Task 3: cards — ArticleCard (post-card/topic-row are dead → skipped)

**Files:** `telemetry.css`; `layouts/partials/article-card.html`; `layouts/_default/single.html`, `layouts/qa/single.html` (shared `.art-meta`/`.art-excerpt`); `layouts/_default/baseof.html` (JS `.art-card`).

**Mapping:** `.art-card`→`.scry-artcard`; `.art-num`→`.scry-artcard__num`; `.art-meta`→`.scry-artcard__meta`; `.art-title`→`.scry-artcard__title`; `.art-excerpt`→`.scry-artcard__excerpt`. **JS (baseof.html:149):** `querySelectorAll('.art-card')`→`querySelectorAll('.scry-artcard')`. `.art-meta`/`.art-excerpt` are reused in single.html/qa-single — rename there too. Do NOT touch `.read-time` (shared atom, no DS card-scoped counterpart this phase). **Skip** `.post-card*`, `.topic-row/.topic-list/.topic-all` (dead CSS).

- [ ] **Step 1: Apply the card mapping** (CSS + article-card.html + single/qa-single + baseof JS).
- [ ] **Step 2: No-orphan verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rnE '\b(art-card|art-num|art-meta|art-title|art-excerpt)\b' themes/scryops/assets/css/telemetry.css themes/scryops/layouts && echo "REVIEW (ensure not the renamed classes)" || echo "clean"
grep -rn "'.art-card'" themes/scryops/layouts/_default/baseof.html && echo "STALE art-card JS" || echo "clean: art-card JS updated"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b3 2>&1 | tail -3
```
Expected: art-card JS updated; no stale `art-*` component classes in class=/selectors; `0 errors`.
- [ ] **Step 3: Commit** → `feat(ds-2b): rename ArticleCard to scry-artcard__* (+ filter JS)`.

---

## Task 4: brand — Wordmark (flat, name-only) + TerminalFeed

**Files:** `telemetry.css`; `layouts/partials/site-top.html` (wordmark); `layouts/_default/index.html` (feed); `layouts/partials/type-glyph.html` (glyph + `tp-*` + `tp-log` fallback string).

**Mapping:**
- `.wordmark`→`.scry-wordmark` (keep flat `<b>` inside — do NOT add DS's nested `__mark`/`__tag`; that's Phase 3). Leave `.foot-logo` (footer variant, no clean DS 1:1) as-is this phase.
- Feed: `.feedwin`→`.scry-feed`; `.feedhdr`→`.scry-feed__hdr`; `.fcursor`→`.scry-feed__cursor`; `.trow`→`.scry-feed__row`; `.tg2`→`.scry-feed__glyph`; `.tt`→`.scry-feed__title`; `.tm`→`.scry-feed__meta`. **Keep `.fp`/`.fa` bare** (DS keeps them). `@keyframes blink`→`@keyframes scry-blink` (update the `animation:` ref too). `.tp-trace/.tp-metric/.tp-prof/.tp-log`→`.scry-tp-trace/…`. **type-glyph.html: update the `default "tp-log"` fallback string** to `scry-tp-log` (it's a Go-template dict literal, not a `class=` attr — easy to miss).
- **CAUTION:** `.tt`/`.tm` are 2-char names — scope edits to their `.scry-feed__row .tt` contexts / exact `class="tt"` occurrences; do NOT blind-replace the substrings.

- [ ] **Step 1: Apply the brand mapping** (CSS + site-top + index feed + type-glyph incl. the fallback literal + keyframes rename).
- [ ] **Step 2: No-orphan verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rnE 'class="(feedwin|feedhdr|fcursor|trow|tg2|tt|tm|wordmark)"|\b@keyframes blink\b|"tp-log"' themes/scryops/layouts themes/scryops/assets/css/telemetry.css && echo "STALE brand tokens remain" || echo "clean: brand renamed"
grep -rn 'scry-blink' themes/scryops/assets/css/telemetry.css && echo "keyframe OK"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b4 2>&1 | tail -3
```
Expected: `clean: brand renamed`, `keyframe OK`, `0 errors`.
- [ ] **Step 3: Commit** → `feat(ds-2b): rename wordmark + terminal feed to scry-*`.

---

## Task 5: eco — Colophon (content file) + FootprintBadge

**Files:** `content/colophon/_index.md` (colophon markup — NOT in theme); `themes/scryops/assets/css/telemetry.css` (colophon + fp rules); `layouts/partials/footer.html` (fp markup). **`footprint.js` needs NO change** (selects by `data-*`).

**Mapping:**
- `.colophon`→`.scry-colophon`; `.co-cmd`→`.scry-colophon__cmd`; `.co-row`→`.scry-colophon__row`; `.co-k`→`.scry-colophon__k`; `.co-v`→`.scry-colophon__v` (incl. descendant rules `.co-v .eco`, `.co-v a`). Edit both the CSS rules AND the hand-authored HTML in `content/colophon/_index.md`.
- `.footprint`→`.scry-fp`; `.fp-pr/.fp-ar/.fp-hi/.fp-eco/.fp-status/.fp-bar/.fp-fill/.fp-note/.fp-method`→`.scry-fp__*`. **Rename ALL FOUR `.footprint` CSS locations:** telemetry.css:194 (`html:not(.js) .footprint`), the main block (~714-727), the `footer .footprint` scoping (~730), and the `@media print` rule (~750). Keep the `.over` modifier (`.scry-fp.over .scry-fp__status/__fill`). footer.html:6-10 markup: rename `class=` values; keep all `data-*` attributes.

- [ ] **Step 1: Apply the eco mapping** (content colophon file + CSS 4 fp locations + footer markup). Do NOT edit footprint.js.
- [ ] **Step 2: No-orphan verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rnE '\b(colophon|co-cmd|co-row|co-k|co-v|footprint|fp-pr|fp-ar|fp-hi|fp-eco|fp-status|fp-bar|fp-fill|fp-note|fp-method)\b' themes/scryops/assets/css/telemetry.css themes/scryops/layouts/partials/footer.html content/colophon/_index.md && echo "REVIEW stale eco classes" || echo "clean"
grep -c '\.scry-fp' themes/scryops/assets/css/telemetry.css   # expect >= 4 fp locations covered
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b5 2>&1 | tail -3
```
Expected: no stale eco classes in class=/selectors (confirm any hits are `data-footprint`/`data-fp-*` attributes, which STAY), build `0 errors`.
- [ ] **Step 3: Commit** — `git add themes/scryops/assets/css/telemetry.css themes/scryops/layouts/partials/footer.html content/colophon/_index.md` → `feat(ds-2b): rename colophon + footprint badge to scry-* (js uses data-attrs, unchanged)`.

---

## Task 6: reading — ReadingPrefs panel (name-only) + prefs.js

**Files:** `themes/scryops/assets/css/telemetry.css`; `layouts/partials/reading-prefs.html`; `themes/scryops/assets/js/prefs.js` (2 class selectors).

**Mapping (PANEL classes only — keep `position:fixed`, no wrapper, no restructure):**
`.pref-btn`→`.scry-prefs__btn`; `.pref-panel`→`.scry-prefs__panel`; `.pref-group`→`.scry-prefs__group`; `.pref-glabel`→`.scry-prefs__glabel`; `.pref-seg`→`.scry-prefs__seg`; `.pref-row`→`.scry-prefs__row` (incl. compound `.pref-row[aria-checked="true"] .pref-sw`); `.pref-l`→`.scry-prefs__l`; `.pref-name`→`.scry-prefs__name`; `.pref-desc`→`.scry-prefs__desc`; `.pref-sw`→`.scry-prefs__sw`.
**JS (prefs.js):** line 62 `querySelector('.pref-panel')`→`('.scry-prefs__panel')`; line 63 `querySelector('.pref-btn')`→`('.scry-prefs__btn')`.
**DO NOT TOUCH:** `html.pref-legible/spacing/reduce/lite`, `html.light/calm` (state classes), `data-pref-*` attributes, `prefs.js` `classList.toggle('pref-'+flag)` logic, or the `head.html` FOUC guard. **Skip** dead `.mode-toggle`.

- [ ] **Step 1: Apply the panel mapping** (CSS + reading-prefs.html + the 2 prefs.js selectors). Rename by EXACT class name, never a `pref-` prefix pattern.
- [ ] **Step 2: No-orphan + state-class-safety verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rnE 'class="(pref-btn|pref-panel|pref-group|pref-glabel|pref-seg|pref-row|pref-l|pref-name|pref-desc|pref-sw)"' themes/scryops/layouts/partials/reading-prefs.html && echo "STALE panel classes" || echo "clean: panel renamed"
grep -n "querySelector('.pref-" themes/scryops/assets/js/prefs.js && echo "STALE prefs.js selector" || echo "clean: prefs.js selectors updated"
grep -nE "classList.toggle\('pref-'\+|pref-legible|pref-spacing|pref-reduce|pref-lite" themes/scryops/assets/js/prefs.js themes/scryops/assets/css/telemetry.css | head   # STATE classes must STILL be present unchanged
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b6 2>&1 | tail -3
```
Expected: panel renamed; prefs.js selectors updated; the STATE class references (`pref-legible` etc. + `classList.toggle('pref-'+`) are STILL present (untouched); `0 errors`.
- [ ] **Step 3: Commit** — `git add themes/scryops/assets/css/telemetry.css themes/scryops/layouts/partials/reading-prefs.html themes/scryops/assets/js/prefs.js` → `feat(ds-2b): rename reading-prefs panel to scry-prefs__* (state classes untouched)`.

---

## Task 7: data — DataTable block class

**Files:** `telemetry.css`; `layouts/shortcodes/obs-comparison-table.html`, `layouts/shortcodes/obs-monitoring-shifts.html`.

**Mapping (block only — keep v1/v2 + current structure; DS rowhead/wrap is Phase 3):** `.obs-table`→`.scry-table` in the CSS selectors and both shortcodes' `<table class="obs-table …">`. **Keep `.v1`/`.v2` bare** (only reparent under `.scry-table`). Do NOT touch `obs-reactive-loop.html` (its `.flow-version.v1/.v2` is a different component). Update the stale comment in `obs-monitoring-shifts.html:1`.

- [ ] **Step 1: Apply the data mapping** (CSS `.obs-table*` selectors → `.scry-table*`; both shortcodes' table class; fix stale comment). Leave v1/v2 class text unchanged.
- [ ] **Step 2: No-orphan verification.**
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -rn 'obs-table' themes/scryops/assets/css/telemetry.css themes/scryops/layouts/shortcodes/obs-comparison-table.html themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html && echo "STALE obs-table" || echo "clean: obs-table renamed"
grep -rn 'flow-version' themes/scryops/layouts/shortcodes/obs-reactive-loop.html && echo "reactive-loop untouched (expected present)"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-2b7 2>&1 | tail -3
```
Expected: `clean: obs-table renamed`, reactive-loop still has its own flow-version (untouched), `0 errors`.
- [ ] **Step 3: Commit** → `feat(ds-2b): rename obs-table to scry-table (v1/v2 + structure unchanged)`.

---

## Task 8: Full rendered-identical verification (dark / light / calm)

No code — acceptance gate. Start a throwaway server (`~/bin/hugo server --buildDrafts --port 1419`), drive Playwright.

- [ ] **Step 1:** Home, a reading page, meet-the-party, a comparison-table article, and a diagram page all load (200) and show **no unstyled elements** (an orphaned renamed class would render unstyled). Snapshot each.
- [ ] **Step 2:** Spot-check computed styles are UNCHANGED vs pre-2b for one element per renamed component (button, callout, insight, tag, tagpill, quote, art-card, wordmark, feed row, colophon row, footprint bar, prefs panel button, scry-table cell) — same color/font/size as before the rename.
- [ ] **Step 3: Behavior checks:** the footprint badge still fills (footprint.js via data-attrs); the reading-prefs gear opens/closes the panel and toggles work (prefs.js selectors updated); theme switching (light/calm state classes) still works; subscribe form still shows its state messages (JS class string updated).
- [ ] **Step 4:** `grep -rnE '\bclass="(btn|callout|insight|tag|tag-pill|art-card|wordmark|feedwin|trow|colophon|co-|footprint|fp-|pref-btn|pref-panel|obs-table)' themes/scryops/layouts content` → zero stale component-class emissions site-wide (excluding STATE classes and kept-bare atoms). Stop the server.

---

## Notes for the implementer

- **The `pref-` prefix trap:** never do a prefix replace — `html.pref-legible/spacing/reduce/lite` are STATE classes that must survive verbatim, and `prefs.js` builds them dynamically. Rename only the exact PANEL class names in Task 6.
- **JS coupling lives in 3 places only:** `baseof.html` (`.art-card`, `.tag`), `prefs.js:62-63` (`.pref-panel`, `.pref-btn`), `index.html:64` (subscribe-msg string). `footprint.js` is data-attribute-driven — do not touch it.
- **Collision-prone bare names** (`.tt/.tm/.v1/.v2`): scope edits to their component selectors/files; never blind-replace the substring.
- **Deferred to Phase 3** (do NOT attempt here): Mascot/cucco, Wordmark nested DOM, ReadingPrefs wrapper/absolute-position, DataTable rowhead/wrap. **Skipped dead CSS** (Phase 4): `.post-card*`, `.topic-row/.topic-list/.topic-all`, `.mode-toggle`.
- Always `~/bin/hugo` (0.145). Stage only each task's named files.
