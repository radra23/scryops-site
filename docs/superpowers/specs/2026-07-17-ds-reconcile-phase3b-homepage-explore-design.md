# DS reconciliation — Phase 3b-B: Homepage "explore" block (PostCard grid + TopicRow rail)

**Date:** 2026-07-17
**Status:** Approved design — pending implementation plan
**Branch:** `feat/ds-reconcile-3b` (off PR #56 tip; 3b-A `0e4d623` already committed)

## Context

Phase 3b was split into **3b-A** (DS-conformance structural items) and **3b-B** (this doc — new homepage UI). 3b-A is done: only the TagPill pill-radius was a real fix (`0e4d623`); the Wordmark `__mark`/`__tag` DOM, the ReadingPrefs `.scry-prefs` wrapper, and the standalone ModeToggle were deliberately **skipped** as no-value churn / regression / dead-code (user agreed — keep-theme-where-ahead).

3b-B wires up **two already-styled-but-unused components** into a new homepage section. Both have complete CSS on legacy names in `telemetry.css`; the work is Hugo templating + a thin responsive layout wrapper, **not** styling.

- `.post-card` / `.post-card-title` (`telemetry.css:570-575`) — the PostCard: surface bg, top-border accent, `.scry-tag` + lowercase title + `.read-time`.
- `.topic-row` / `.topic-name` / `.topic-badge` (`telemetry.css:492-497`) — the TopicRow: name + count badge, left-border accent, hover-cyan; sits in a `.topic-list` (`:490`) flex-wrap column (`.topic-row` has `flex-basis:100%` → stacks full-width).

## Decisions (locked)

- **Layout A — "Explore block."** Keep the signature terminal `.scry-feed`; add **one** new `<section class="front-explore">` between the feed and the subscribe partial, as a 2-column grid: PostCard grid (left, wider) + TopicRow rail (right).
- **PostCard grid content:** the **6 next-latest pieces after the feed** — same query as the feed (`site.RegularPages` where `Type` in `guides/articles/howtos/qa`, `sort … Date desc`), sliced `after 6 | first 6` → items 7–12. Feed + grid = the 12 most recent, **zero overlap**, fully automatic (no front-matter flags).
- **TopicRow rail source:** the **top 6 tags by article count** from `site.Taxonomies.tags` (real counts, real `/tags/<term>/` links, self-maintaining). NOT the curated `Params.topics` list (its slugs — `traces`, `distributed-systems` — don't map cleanly to tag terms/counts).
- **Hero topic-chips:** unchanged. The flat quick-scan chips stay; the rail adds the count/browse affordance (complementary, not redundant).
- Reuse the existing `.post-card` / `.topic-row` / `.topic-list` classes verbatim — no rename, no restyle. Only additive layout CSS.
- Build/verify with Hugo 0.145. No AI commit attribution.

## Component 1 — PostCard grid ("more reading")

**Modify:** `themes/scryops/layouts/_default/index.html`, `themes/scryops/assets/css/telemetry.css`.

Inside `front-explore`, left column. Hugo:

```go-html-template
{{ $all := sort (where site.RegularPages "Type" "in" (slice "guides" "articles" "howtos" "qa")) "Date" "desc" }}
{{ $more := first 6 (after 6 $all) }}
```

The feed's existing `$latest := first 6 …` and this `$more := first 6 (after 6 …)` derive from the **same sort**, so they never overlap and never need a manual exclusion list. (Reuse a single shared `$all`/`$sorted` binding so the two sections can't drift.)

Each card (matches the `.post-card` CSS contract — `.scry-tag`, `.post-card-title`, `.read-time`):

```go-html-template
{{ range $more }}
<a class="post-card" href="{{ .RelPermalink }}">
  <span class="scry-tag">{{ .Type }}</span>
  <span class="post-card-title">{{ .Title }}</span>
  {{ with .Params.readtime }}<span class="read-time">{{ . }}m</span>{{ end }}
</a>
{{ end }}
```

Wrapped in a `.post-grid` container. **New CSS:** `.post-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.7rem;min-width:0}` (exact minmax/gap tunable in the plan; `min-width:0` guards the grid-overflow trap hit in 3a).

If fewer than 7 qualifying pieces exist, `after 6` yields an empty slice → the grid renders nothing; the section should self-hide when empty (guard the whole left column, or the section, on `len $more`).

## Component 2 — TopicRow rail ("browse by topic")

**Modify:** `themes/scryops/layouts/_default/index.html` (same section, right column).

```go-html-template
<nav class="topic-list">
  {{ range first 6 site.Taxonomies.tags.ByCount }}
  <a class="topic-row" href="{{ .Page.RelPermalink }}">
    <span class="topic-name">{{ .Page.Title }}</span>
    <span class="topic-badge">{{ .Count }}</span>
  </a>
  {{ end }}
</nav>
```

`.ByCount` returns an `OrderedTaxonomy` already sorted by article count descending; each entry exposes `.Count` and `.Page` (the term page). `.topic-list` + `.topic-row` (with `flex-basis:100%`) stack the rows full-width in the column; `.Page.RelPermalink` / `.Page.Title` give the canonical `/tags/<term>/` URL and display-cased term name (matching the /tags/ page). **Confirm the `.ByCount` field names against a real Hugo 0.145 build in the plan** (`.Page.Title` vs `.Term` for the display label) — the top-6-by-count output must match the /tags/ page before finalizing.

## Layout & headings

**New CSS** — the `front-explore` 2-col container:
- `.front-explore{display:grid;grid-template-columns:2fr 1fr;gap:2rem;margin-top:...;min-width:0}` with children `min-width:0` (grid-overflow guard).
- Collapse to a single column below the mobile breakpoint used elsewhere in the theme (match the existing `@media` query; stack cards above rail).
- A section label per column reusing the `.topics-label` style (`telemetry.css:489`) — "more reading" / "browse by topic" (sentence case, matching the site's lowercase editorial voice).

No new colors, fonts, or tokens — everything resolves through existing Telemetry vars, so dark/light/calm all inherit for free.

## Verification

Build with Hugo 0.145 (`0 errors`). On a preview (dark + light + calm):
1. Homepage shows, in order: hero (chips intact) → terminal feed (6 latest) → **new explore block** → subscribe.
2. **PostCard grid:** 6 cards, each with a type tag + lowercase title + read-time; hover shows the green top-border + tint; **none of the 6 duplicates a feed item**; each links to the right piece.
3. **TopicRow rail:** exactly the top 6 tags by count, each showing name + numeric badge matching the /tags/ page; hover shows cyan; each links to `/tags/<term>/`.
4. **Responsive:** at ~380px the 2-col collapses to 1 col (cards then rail), no horizontal page scroll (grid `min-width:0` holds).
5. **Themes:** the block recolors correctly in light and calm (surfaces/borders/accents via vars).
6. Nothing above (hero, feed) or below (subscribe) regressed.

## Out of scope for 3b-B

- 3b-A items (already resolved: TagPill done; Wordmark/ReadingPrefs/ModeToggle skipped).
- 3c (Mascot/cucco rebuild) and Phase 4 (dead-CSS cleanup — note the `.post-card`/`.topic-row` CSS moves from "dead" to "live" here, so it must be **removed from the Phase-4 deletion list**).
- Extracting PostCard/TopicRow into standalone partials (inline in `index.html` matches the existing inline `.scry-feed__row` pattern in the same file; extract later only if reused elsewhere).
- Changing the hero chips or the curated `Params.topics` list.

## Success criteria

The homepage gains an "explore" block below the terminal feed: a `.post-card` grid of the 6 next-latest pieces (no overlap with the feed) beside a `.topic-row` rail of the top 6 tags by count (with counts + working `/tags/` links). Both reuse existing CSS verbatim; only additive layout CSS is introduced; the block is responsive and theme-correct across dark/light/calm; Hugo builds clean; the feed, hero, and subscribe sections are unchanged.
