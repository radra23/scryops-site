# Homepage "explore" block (Phase 3b-B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full-width "explore" block below the homepage hero/feed area — a PostCard grid of the 6 next-latest pieces beside a TopicRow rail of the top 6 tags by count — reusing already-styled but unused CSS.

**Architecture:** The homepage template (`_default/index.html`) gains one new `<section class="front-explore">` placed as a sibling *after* the existing `.front` grid (which is a hero|feed 2-col area) and *before* the subscribe partial. The section is its own 2-col grid (cards | rail). Both inner components reuse existing verbatim CSS (`.post-card`/`.post-grid`, `.topic-row`/`.topic-list`); only the `.front-explore` container CSS is new. Data comes from a shared date-sorted page slice (feed = first 6, grid = next 6) and `site.Taxonomies.tags.ByCount`.

**Tech Stack:** Hugo 0.145 (build with `/Users/jonhdoe/bin/hugo`, NOT the 0.159 on PATH), Go html/template, existing Telemetry CSS token system.

## Global Constraints

- Build/verify with Hugo 0.145 only: `/Users/jonhdoe/bin/hugo`. CI `validate` runs `python3 scripts/verify_visuals.py` (also the local pre-commit hook) — it must stay green.
- No AI commit attribution: omit `Co-Authored-By` trailers and any Claude footer.
- Reuse `.post-card` / `.post-grid` / `.topic-row` / `.topic-list` / `.topics-label` classes verbatim — no rename, no restyle. Only `.front-explore` layout CSS is new.
- No new colors/fonts/tokens — everything resolves through existing Telemetry vars so dark/light/calm inherit automatically.
- The live stylesheet is `themes/scryops/assets/css/telemetry.css` (fingerprinted via Hugo Pipes). `static/css/style.css` is dead — never edit it.
- Match the homepage mobile breakpoint: `@media (max-width:820px)` (that's where `.front` collapses to 1 col).

---

### Task 1: Explore section scaffold + PostCard grid

**Files:**
- Modify: `themes/scryops/layouts/_default/index.html`
- Modify: `themes/scryops/assets/css/telemetry.css`

**Interfaces:**
- Consumes: existing `.post-card` / `.post-grid` CSS (`telemetry.css:569-575`); existing `.topics-label` CSS (`telemetry.css:489`).
- Produces: a `$sorted` template variable (date-desc slice of `guides/articles/howtos/qa` regular pages) reused in Task 2's section; a `<section class="front-explore">` whose right column Task 2 fills with the rail.

Current `index.html` (for reference — the feed currently declares its own `$latest`):

```go-html-template
{{ define "main" }}
<div class="front">
  <section class="front-hero"> ... </section>
  {{ $latest := first 6 (sort (where site.RegularPages "Type" "in" (slice "guides" "articles" "howtos" "qa")) "Date" "desc") }}
  <section class="front-feed">
    <div class="scry-feed"> ... {{ range $latest }} ... {{ end }} </div>
  </section>
</div>
{{ partial "subscribe-form.html" . }}
{{ end }}
```

- [ ] **Step 1: Write the failing test (build + assert the grid is absent)**

Run against the current tree (no explore section yet):

```bash
cd /Users/jonhdoe/Repository/scryops-site
rm -rf /tmp/hugo-3bb && /Users/jonhdoe/bin/hugo --quiet --destination /tmp/hugo-3bb
grep -c 'class="post-card"' /tmp/hugo-3bb/index.html
```

Expected: `0` (grid not present yet). This is the red state.

- [ ] **Step 2: Refactor the feed query to a shared `$sorted` binding**

In `themes/scryops/layouts/_default/index.html`, replace the single `$latest` declaration line:

```go-html-template
  {{ $latest := first 6 (sort (where site.RegularPages "Type" "in" (slice "guides" "articles" "howtos" "qa")) "Date" "desc") }}
```

with a shared sort plus two derived slices:

```go-html-template
  {{ $sorted := sort (where site.RegularPages "Type" "in" (slice "guides" "articles" "howtos" "qa")) "Date" "desc" }}
  {{ $latest := first 6 $sorted }}
  {{ $more   := first 6 (after 6 $sorted) }}
```

(The feed's `{{ range $latest }}` is unchanged. `$more` = items 7–12 by date; `after 6` skips the first 6, so feed and grid never overlap.)

- [ ] **Step 3: Add the explore section (left column: PostCard grid)**

In `themes/scryops/layouts/_default/index.html`, immediately AFTER the `</div>` that closes `<div class="front">` and BEFORE `{{ partial "subscribe-form.html" . }}`, insert:

```go-html-template
{{ if gt (len $more) 0 }}
<section class="front-explore">
  <div class="front-explore__col">
    <span class="topics-label">more reading</span>
    <div class="post-grid">
      {{ range $more }}
      <a class="post-card" href="{{ .RelPermalink }}">
        <span class="scry-tag">{{ .Type }}</span>
        <span class="post-card-title">{{ .Title }}</span>
        {{ with .Params.readtime }}<span class="read-time">{{ . }}m</span>{{ end }}
      </a>
      {{ end }}
    </div>
  </div>
</section>
{{ end }}
```

(`$more` is in scope here because it was declared at the top level of the `define "main"` block, not inside a nested `range`/`with`. The right column — the rail — is added in Task 2.)

- [ ] **Step 4: Add the `.front-explore` container CSS**

In `themes/scryops/assets/css/telemetry.css`, immediately AFTER the `.front-feed{padding:24px 0}` rule (line 667), add:

```css
.front-explore{max-width:1080px;margin:0 auto;padding:0 28px 90px;display:grid;grid-template-columns:2fr 1fr;gap:44px;align-items:start}
.front-explore__col{min-width:0}
```

Then, inside the existing `@media (max-width:820px){ ... }` block (the one starting at line ~683 that already contains `.front{grid-template-columns:1fr;...}`), add one line so the explore block also collapses to a single column:

```css
  .front-explore{grid-template-columns:1fr;gap:26px;padding-bottom:48px}
```

(`min-width:0` on the column guards the CSS-grid overflow trap hit in Phase 3a — without it a wide card title would push the column past its track.)

- [ ] **Step 5: Run the test to verify the grid now renders 6 cards**

```bash
cd /Users/jonhdoe/Repository/scryops-site
rm -rf /tmp/hugo-3bb && /Users/jonhdoe/bin/hugo --quiet --destination /tmp/hugo-3bb 2>&1 | tail -3
echo "exit: $?"
grep -c 'class="post-card"' /tmp/hugo-3bb/index.html
```

Expected: build exit `0`; grep prints `6`.

- [ ] **Step 6: Verify feed/grid non-overlap**

```bash
cd /Users/jonhdoe/Repository/scryops-site
echo "--- feed (first 6) ---"
grep -o 'class="scry-feed__title">[^<]*' /tmp/hugo-3bb/index.html | sed 's/.*>//'
echo "--- grid (next 6) ---"
grep -o 'class="post-card-title">[^<]*' /tmp/hugo-3bb/index.html | sed 's/.*>//'
```

Expected: two disjoint lists of 6 titles each (no title appears in both). If any overlap, the `after 6` slice is wrong — stop and fix before committing.

- [ ] **Step 7: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/layouts/_default/index.html themes/scryops/assets/css/telemetry.css
git commit -m "feat(home): add explore block with more-reading PostCard grid

New full-width .front-explore section below the hero/feed area. Shares a
single date-sorted page slice: feed = first 6, grid = next 6 (after 6), so
the two never overlap. Reuses the existing .post-card/.post-grid CSS; adds
only the .front-explore 2-col container (collapses at 820px)."
```

Expected: pre-commit `verify_visuals.py` prints "all hard checks passed".

---

### Task 2: TopicRow rail (browse by topic)

**Files:**
- Modify: `themes/scryops/layouts/_default/index.html`

**Interfaces:**
- Consumes: the `<section class="front-explore">` from Task 1; existing `.topic-list` / `.topic-row` / `.topic-name` / `.topic-badge` CSS (`telemetry.css:490-497`).
- Produces: nothing downstream (final content task).

- [ ] **Step 1: Write the failing test (rail absent)**

```bash
cd /Users/jonhdoe/Repository/scryops-site
rm -rf /tmp/hugo-3bb && /Users/jonhdoe/bin/hugo --quiet --destination /tmp/hugo-3bb
grep -c 'class="topic-row"' /tmp/hugo-3bb/index.html
```

Expected: `0` (red state).

- [ ] **Step 2: Add the rail as the section's right column**

In `themes/scryops/layouts/_default/index.html`, inside `<section class="front-explore">`, immediately AFTER the closing `</div>` of `.front-explore__col` (the cards column) and BEFORE `</section>`, insert:

```go-html-template
  <div class="front-explore__col">
    <span class="topics-label">browse by topic</span>
    <nav class="topic-list">
      {{ range first 6 site.Taxonomies.tags.ByCount }}
      <a class="topic-row" href="{{ .Page.RelPermalink }}">
        <span class="topic-name">{{ .Page.Title }}</span>
        <span class="topic-badge">{{ .Count }}</span>
      </a>
      {{ end }}
    </nav>
  </div>
```

(`site.Taxonomies.tags.ByCount` returns an `OrderedTaxonomy` already sorted by article count descending; each entry exposes `.Count` and `.Page` — the term's page, whose `.Title` is the display-cased term name and `.RelPermalink` is `/tags/<term>/`.)

- [ ] **Step 3: Run the test — rail renders 6 rows**

```bash
cd /Users/jonhdoe/Repository/scryops-site
rm -rf /tmp/hugo-3bb && /Users/jonhdoe/bin/hugo --quiet --destination /tmp/hugo-3bb 2>&1 | tail -3
echo "exit: $?"
grep -c 'class="topic-row"' /tmp/hugo-3bb/index.html
```

Expected: build exit `0`; grep prints `6`.

- [ ] **Step 4: Verify rail content matches the /tags/ page (names, counts, links)**

```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -o 'class="topic-name">[^<]*\|class="topic-badge">[^<]*\|href="/tags/[^"]*' /tmp/hugo-3bb/index.html | sed 's/class="[^"]*">//'
```

Expected: 6 topic names + 6 numeric badges + 6 `/tags/<term>/` hrefs. The top entry must be the site's most-used tag with its count (per the /tags/ page: `Observability` with `78`). If `topic-name` is blank, `.Page.Title` isn't resolving — switch the label to `{{ .Page.LinkTitle }}` and re-run this step. Confirm each count equals the parenthesized number on `/tmp/hugo-3bb/tags/index.html` for the same term:

```bash
grep -o '>[A-Za-z][^<(]*([0-9]*)' /tmp/hugo-3bb/tags/index.html | head -8
```

- [ ] **Step 5: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/layouts/_default/index.html
git commit -m "feat(home): add TopicRow rail to the explore block

Right column of .front-explore: top 6 tags by article count from
site.Taxonomies.tags.ByCount, each linking to its /tags/<term>/ page with
a count badge. Reuses the existing .topic-list/.topic-row CSS."
```

Expected: pre-commit hook "all hard checks passed".

---

### Task 3: Cross-theme + responsive verification, and Phase-4 list correction

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css` (only if a spacing issue is found in browser verification)
- Reference: the memory phase tracker (update the Phase-4 dead-CSS list)

**Interfaces:**
- Consumes: the complete `.front-explore` section from Tasks 1–2.
- Produces: verified, theme-correct, responsive homepage; corrected Phase-4 cleanup scope.

- [ ] **Step 1: Start a preview server**

If port 1313 is occupied by a stale server, free it first (`lsof -ti:1313 | xargs kill`), then:
Use `preview_start` with `{name:"hugo-dev"}`, then navigate the returned tab to `http://localhost:1313/`.

- [ ] **Step 2: Verify the explore block in dark theme**

Read the page and confirm: below the hero/feed area sits an explore section with a "more reading" cards column (6 cards, each type tag + lowercase title + read-time) and a "browse by topic" rail (6 rows, name + count badge). Take a screenshot. Confirm no card duplicates a feed row visually.

Run this computed-style check in the browser (via `javascript_tool`):

```javascript
JSON.stringify({
  cards: document.querySelectorAll('.post-card').length,
  rows: document.querySelectorAll('.topic-row').length,
  cols: getComputedStyle(document.querySelector('.front-explore')).gridTemplateColumns,
  topTopic: document.querySelector('.topic-name')?.textContent,
  topCount: document.querySelector('.topic-badge')?.textContent
})
```

Expected: `cards:6, rows:6`, `cols` shows two tracks (e.g. `"... ..."` two values), `topTopic`/`topCount` = the site's top tag + count.

- [ ] **Step 3: Verify light and calm themes**

Toggle the theme (the reading-prefs panel, or set `document.documentElement.className`): for `html.light` and `html.calm`, confirm the cards' surface/border and the rail's accents recolor correctly (no hardcoded colors, no invisible text). Screenshot each.

- [ ] **Step 4: Verify mobile collapse at 380px**

`resize_window` to 380px wide. Confirm `.front-explore` stacks to a single column (cards above rail) and there is NO horizontal page scroll:

```javascript
JSON.stringify({
  cols: getComputedStyle(document.querySelector('.front-explore')).gridTemplateColumns,
  docWidth: document.documentElement.scrollWidth,
  viewport: window.innerWidth,
  overflow: document.documentElement.scrollWidth > window.innerWidth
})
```

Expected: `cols` is a single track; `overflow:false`. If `overflow:true`, add `min-width:0` where missing / check `.post-grid` minmax, fix in `telemetry.css`, rebuild, re-run. Commit any fix with message `fix(home): <description>`.

- [ ] **Step 5: Correct the Phase-4 dead-CSS list**

The `.post-card`, `.post-grid`, `.topic-row`, `.topic-name`, `.topic-badge`, and `.topic-list` rules are now LIVE (used by this section). Update the memory file `scryops-ds-reconciliation-phases.md`: in the Phase-4 line, remove `.post-card` and `.topic-row/list` from the "dead CSS to delete" set and note they went live in 3b-B. (No code change — this prevents a later phase from deleting live CSS.)

- [ ] **Step 6: Final commit (if any CSS fix was made in Step 4)**

If Step 4 required no fix, there is nothing to commit here — the section is already committed by Tasks 1–2; skip. Otherwise the fix was already committed in Step 4. Confirm the tree is clean:

```bash
cd /Users/jonhdoe/Repository/scryops-site && git status -s
```

Expected: clean (or only the intended fix commit in history).

---

## Self-Review

**Spec coverage:**
- Layout A / new `front-explore` section between feed and subscribe → Task 1 Step 3. ✓
- PostCard grid = feed query sliced `after 6 | first 6`, no overlap → Task 1 Steps 2, 6. ✓
- Card markup (`.scry-tag`/`.post-card-title`/`.read-time`) → Task 1 Step 3. ✓
- Empty-state self-hide (`if gt (len $more) 0`) → Task 1 Step 3. ✓
- TopicRow rail = `tags.ByCount | first 6`, name+count+`/tags/` link → Task 2 Steps 2, 4. ✓
- `.ByCount` field-name verification (`.Page.Title` vs fallback) → Task 2 Step 4. ✓
- Reuse existing CSS; only `.front-explore` new → Task 1 Step 4 (and `.post-grid` already exists, so NOT re-added). ✓
- Responsive collapse at 820px + `min-width:0` guards → Task 1 Step 4, Task 3 Step 4. ✓
- Dark/light/calm theme-correct → Task 3 Steps 2–3. ✓
- Hero chips unchanged → not touched by any task. ✓
- Phase-4 list correction (CSS now live) → Task 3 Step 5. ✓

**Placeholder scan:** No TBD/TODO; every code step shows exact content; every test step shows an exact command with expected output. ✓

**Type/name consistency:** `$sorted`/`$latest`/`$more` defined in Task 1 Step 2, `$more` consumed in Step 3; `.front-explore` / `.front-explore__col` used consistently across Task 1 CSS, Task 2 markup, Task 3 checks; `.topic-name`/`.topic-badge` match the CSS at `:494-497`. ✓
