# Design: inline `langswitch` — multi-language code switcher (replacing `codetabs`)

- **Date:** 2026-06-25
- **Status:** Approved (design); pending spec review
- **Repo:** scryops-site (Hugo, custom `scryops` theme)

## Goal

Replace the existing `codetabs` shortcode with `langswitch`, a multi-language code
switcher ported from the "Multi-language prototype showcase" prototype. Readers pick
a programming language **once**; the choice is shared across every code block on the
page and **persisted across reloads** (and pages) via `localStorage`. Top-5 languages
render as tabs, the rest behind a `+N` overflow menu. Server-side Chroma highlighting
is reused; no client-side highlighter ships.

## Decisions (already made with the user)

1. **Integration model: Replace `codetabs`.** `langswitch` becomes the single
   code-switching shortcode; `codetabs` is removed after migration.
2. **Authoring model: Inline (enhance the prototype).** Code stays written inline as
   fenced blocks inside the shortcode (as `codetabs` works today). We do **not** adopt
   the prototype's central `data/codesamples.yaml`. The prototype's headline UX (global
   persisted choice, overflow menu, smart-default hint, copy, full a11y) is preserved.

## Current state

- `themes/scryops/layouts/shortcodes/codetabs.html` — paired shortcode; wraps
  consecutive fenced blocks into tabs. Per-block local state, no persistence, no
  overflow, no shared choice. Inlines its own `<style>`/`<script>` once per page.
- Chroma styling lives in `themes/scryops/static/css/style.css` as a **global**
  class-based `.chroma` palette (Monokai-ish). `hugo.toml` already sets
  `markup.highlight.noClasses = false` (required for class-based output).
- `codetabs` usage to migrate — **10 groups across 4 files**, every group the same
  three languages (`.NET`/`csharp`, `go`, `python`):
  - `content/howtos/instrument-python-service-opentelemetry.md` — 4 groups
  - `content/howtos/wire-trace-ids-into-logs.md` — 2 groups
  - `content/howtos/run-jaeger-locally-with-opentelemetry.md` — 1 group
  - `content/guides/high-throughput-logging.md` — 3 groups

## Architecture

A single paired shortcode plus a JS engine and CSS, all self-contained in the theme
(the theme already owns `codetabs` and the `.chroma` palette).

```
themes/scryops/layouts/shortcodes/langswitch.html   paired shortcode
themes/scryops/assets/js/langswitch.js              client engine (Hugo Pipes)
themes/scryops/assets/css/langswitch.css            switcher chrome styles
themes/scryops/data/langmeta.yaml                   fence-lang -> {label, file}
```

**Dropped from the prototype:** `chroma-scryops.css` (use the theme's global `.chroma`
palette so switcher code matches every other code block); `data/codesamples.yaml`
(inline model needs no central data); the self-closing `key=` shortcode form.

### Shortcode (`langswitch.html`)

Paired shortcode: `{{< langswitch >}} …fenced blocks… {{< /langswitch >}}`, optional
`default=` param.

- **Once per page** (guarded by `.Page.Store`): inject `langswitch.css` and
  `langswitch.js` via Hugo Pipes (`resources.Get` → `minify` → `fingerprint`), and emit
  `<script>window.scryLangMeta = {{ .Site.Data.langmeta | jsonify }}</script>` so the JS
  can resolve labels/filenames. (`langswitch.js` is loaded `defer`, so the inline meta
  script runs first.)
- **Per call:** render the chrome bar (traffic-light dots, filename slot, Copy button),
  an empty tab row (`role="tablist"`), the smart-default hint row, and
  `<div class="ls-panels">{{ .Inner | markdownify }}</div>` — Hugo highlights the inner
  fences into `.highlight > pre.chroma > code[data-lang]`. Set `data-default` from the
  `default=` param (fallback `python`).

### Client engine (`langswitch.js`)

Adapted from the prototype. **Key change:** panels are sourced from inner `.highlight`
blocks (read `data-lang` off each `<code>`), not from server-rendered `[data-ls-panel]`
divs; labels/filenames come from `window.scryLangMeta`, not DOM `data-*` attributes.

Preserved behavior:
- One **global** selected language across all blocks; persisted to
  `localStorage["scry:lang"]`. Changing any block re-renders all and fires a
  `scry:langchange` event.
- Resolution order on load: saved choice → `?lang=` query param → optional
  `window.scryDetectLang()` host hook → block `default`. (`?lang=` enables shareable
  deep links like `…?lang=go`.)
- **Top-5 tabs + `+N` overflow**; the active language is promoted into the visible row
  if it would otherwise live in the overflow.
- **Smart-default hint** shown only until the reader's first explicit pick.
- Copy button (reads the active block's `<pre>` text; `aria-live` feedback).
- A11y: `role="tablist"/"tab"`, `aria-selected`, ←/→ arrow nav, overflow menu closes on
  outside-click and `Escape`, `prefers-reduced-motion` respected.
- **Alias normalization** so author fences map to canonical ids: `cs`→`csharp`,
  `js`→`javascript`, `golang`→`go`, `py`→`python`, `yml`→`yaml`.
- `POPULAR` order array (drives top-5 vs overflow) lives at the top of the file:
  `["python","javascript","go","java","csharp","rust","ruby"]`. For the migrated
  content (python/go/csharp) all three sit in the top-5 — no overflow appears.

### `langmeta.yaml`

Keyed by **fence language** (what authors type), single source for tab label and the
terminal filename:

```yaml
python:     { label: "Python",  file: "app.py" }
javascript: { label: "Node.js", file: "index.js" }
go:         { label: "Go",      file: "main.go" }
java:       { label: "Java",    file: "Main.java" }
csharp:     { label: ".NET",    file: "Program.cs" }
rust:       { label: "Rust",    file: "main.rs" }
ruby:       { label: "Ruby",    file: "app.rb" }
```

Only languages actually present in a block render; the full list is kept for future use.

### Chroma reconciliation

Do **not** load the prototype's `chroma-scryops.css`. The inner fences render through the
same highlighter as all other code, so they inherit the theme's global `.chroma` palette
automatically — one palette site-wide. `langswitch.css` only styles the switcher chrome
and neutralizes the inner `.highlight` wrapper's default margin/spacing inside
`.langswitch` (padding + horizontal scroll handled on the panel area), mirroring how
`codetabs` neutralizes `.highlight`.

### Smart-default hint — honesty fix

The prototype's hint claims "detected from your project," which a static Hugo site can't
truthfully produce. Reword to: **"Showing <Language> — pick your language and we'll
remember it."** Shown once until the first explicit choice, then never again. The
`window.scryDetectLang` hook and `?lang=` support remain (harmless, optional), but no
copy claims detection.

## Migration

For each of the 10 groups in the 4 files: rename `{{< codetabs >}}` → `{{< langswitch >}}`
and `{{< /codetabs >}}` → `{{< /langswitch >}}`. Inner fenced blocks stay exactly as-is
(```` ```csharp ````/```` ```go ````/```` ```python ````). `csharp` maps to the ".NET"
label via `langmeta`. No `default=` needed (site default `python` applies); add one only
where a specific block should lead with a different language. Content prose, tags, and
visuals are untouched, so the tag/visual CI gates are unaffected.

## Retire `codetabs`

After migration and a clean build, delete
`themes/scryops/layouts/shortcodes/codetabs.html` and grep the repo to confirm zero
remaining `codetabs` references in `content/`.

## Verification

1. `hugo` builds with no shortcode/template errors.
2. Preview (`hugo server`):
   - Tabs render on each migrated block; filename shows in the chrome bar.
   - Picking a language on one block switches **all** blocks on the page.
   - Choice **survives reload** and carries to another page.
   - `?lang=go` deep link selects Go on first load.
   - Copy copies the active language's code.
   - Keyboard: ←/→ moves across tabs; `Escape` closes overflow.
   - Code token colors match surrounding (non-switcher) code blocks.
3. Accessibility: tablist roles/`aria-selected` present; reduced-motion honored.

## Out of scope (YAGNI)

- No backend/edge language detection (static site).
- No central sample library (`codesamples.yaml`).
- No new languages beyond what content uses (langmeta keeps the 7 for future use).
- No restyling of the global `.chroma` palette.

## Risks / notes

- **Dirty working tree:** repo is on branch `finalize-howtos` with unrelated WIP;
  `instrument-python` and `run-jaeger` are already modified, and `.env` is untracked
  (must never be staged). Migration edits operate on current working-tree content. Branch
  strategy for this feature to be confirmed with the user.
- **Global persistence is intentional:** all switchers on a page move together. For the
  step-by-step how-tos this is the desired behavior (pick your SDK once, all steps follow).
- If a future block omits the globally chosen language, the engine falls back to that
  block's `default`/first available — no empty panels.
