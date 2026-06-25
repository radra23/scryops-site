# Inline `langswitch` Multi-Language Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `codetabs` shortcode with an enhanced inline `langswitch` that gives readers one globally-shared, persisted programming-language choice across every code block on the site.

**Architecture:** A single paired Hugo shortcode (`{{< langswitch >}} …fenced blocks… {{< /langswitch >}}`) renders inner code via the theme's server-side Chroma classes. A vanilla-JS engine discovers each block's language from `data-lang`, builds a top-5-tabs + `+N`-overflow row, and drives one global selection persisted to `localStorage`. Labels/filenames come from a small `data/langmeta.yaml` exposed to JS as `window.scryLangMeta`.

**Tech Stack:** Hugo (custom `scryops` theme), Hugo Pipes (`resources.Get` → minify → fingerprint), Goldmark + Chroma (class-based highlighting), vanilla ES5-compatible JS, CSS using the theme's design tokens.

## Global Constraints

- **No new code palette:** do NOT add `chroma-scryops.css`. Inner code inherits the theme's global `.chroma` palette in `themes/scryops/static/css/style.css`. One palette site-wide.
- **Highlighting config already correct:** `hugo.toml` has `markup.highlight.noClasses = false`. Do not change it.
- **Verification is build + browser, not unit tests:** this repo has no JS/CSS test runner. Each task's gate is `hugo` building with no `ERROR`/template failure, plus browser behavior via the preview/Playwright tools.
- **Pre-commit hook runs `python3 scripts/verify_visuals.py`** (tags + visuals). It must pass before each commit. Migration touches only shortcode tags, not tags/visuals, so it stays green.
- **Never stage `.env` or unrelated WIP.** Stage only the exact files each task lists. Work is on branch `feat/langswitch`.
- **ES5-compatible JS** (no arrow functions / template literals in the shipped `.js`) to match the prototype's style and avoid surprises through minify.
- **Every inner block must declare a language** (```` ```python ````, etc.); an unlabeled block is ignored by the switcher.

---

## File Structure

- `themes/scryops/data/langmeta.yaml` *(create)* — fence-language → `{label, file}`. Single source for tab labels and the terminal filename; exposed to JS as `window.scryLangMeta`.
- `themes/scryops/assets/css/langswitch.css` *(create)* — switcher chrome (bar, tabs, overflow menu, hint, panels). Neutralizes the theme's `.prose pre` border/margin/background inside `.langswitch`; inherits theme padding/font for code parity.
- `themes/scryops/assets/js/langswitch.js` *(create)* — the engine: global persisted selection, top-5+overflow, smart-default hint (first switcher only), copy, ARIA tablist + keyboard, alias normalization. Sources panels from inner `.highlight` blocks; labels/files from `window.scryLangMeta`.
- `themes/scryops/layouts/shortcodes/langswitch.html` *(create)* — paired shortcode. Injects CSS/JS + `window.scryLangMeta` once per page; renders chrome + empty tab row + hint + `.ls-panels` wrapping `{{ .Inner | markdownify }}`.
- `content/howtos/run-jaeger-locally-with-opentelemetry.md` *(modify)* — 1 group (smoke test).
- `content/howtos/instrument-python-service-opentelemetry.md` *(modify)* — 4 groups.
- `content/howtos/wire-trace-ids-into-logs.md` *(modify)* — 2 groups.
- `content/guides/high-throughput-logging.md` *(modify)* — 3 groups.
- `themes/scryops/layouts/shortcodes/codetabs.html` *(delete)* — retired after migration.

---

## Task 1: Build the langswitch feature + smoke-test on run-jaeger

Creates all four feature files and migrates the single-group file as an end-to-end smoke test (build + browser). This is the smallest deliverable that proves the whole mechanism.

**Files:**
- Create: `themes/scryops/data/langmeta.yaml`
- Create: `themes/scryops/assets/css/langswitch.css`
- Create: `themes/scryops/assets/js/langswitch.js`
- Create: `themes/scryops/layouts/shortcodes/langswitch.html`
- Modify: `content/howtos/run-jaeger-locally-with-opentelemetry.md` (the one `codetabs` group)

**Interfaces:**
- Produces (DOM contract the JS relies on): shortcode root `div.langswitch[data-langswitch][data-default]` containing `[data-ls-tabs]`, `[data-ls-file]`, `[data-ls-copy]`, `[data-ls-hint]` with `[data-ls-hint-label]`, and `[data-ls-panels]` holding Hugo `.highlight` blocks whose `<code>` carries `data-lang`.
- Produces (JS globals): reads `window.scryLangMeta` (object: `{ <fenceLang>: {label, file} }`); fires `window` event `scry:langchange` with `{detail:{lang}}`; persists `localStorage["scry:lang"]`.

- [ ] **Step 1: Create `themes/scryops/data/langmeta.yaml`**

```yaml
# Tab label + terminal filename per fence language for the {{< langswitch >}} shortcode.
# Keyed by the language token authors write in fences (```python, ```csharp, ...).
# Exposed to langswitch.js as window.scryLangMeta. Add a language by adding a row;
# only languages actually present in a block render.
python:     { label: "Python",  file: "app.py" }
javascript: { label: "Node.js", file: "index.js" }
go:         { label: "Go",      file: "main.go" }
java:       { label: "Java",    file: "Main.java" }
csharp:     { label: ".NET",    file: "Program.cs" }
rust:       { label: "Rust",    file: "main.rs" }
ruby:       { label: "Ruby",    file: "app.rb" }
```

- [ ] **Step 2: Create `themes/scryops/assets/css/langswitch.css`**

```css
/* langswitch.css — scryops multi-language code switcher (inline edition).
 * Styles the switcher chrome only; inner code uses the theme's global .chroma
 * palette. Square corners, hairline borders, single amber accent. Falls back to
 * literal colors if the theme tokens are absent.
 */
.langswitch {
  --ls-amber: var(--amber, #F5A623);
  --ls-surface: var(--surface, #161616);
  --ls-surface-2: var(--surface-2, #1C1C1C);
  --ls-border: var(--border, #2A2A2A);
  --ls-border-strong: var(--border-strong, #3A3A3A);
  --ls-text: var(--text, #F0EEE8);
  --ls-muted: var(--muted, #9A9A92);
  --ls-mono: var(--font-mono, "Commit Mono", ui-monospace, "SFMono-Regular", Menlo, monospace);
  --ls-wash: var(--wash-amber, rgba(245, 166, 35, 0.06));

  background: var(--ls-surface);
  border: 1px solid var(--ls-border);
  border-top: 3px solid var(--ls-amber);
  border-radius: 0;
  font-family: var(--ls-mono);
  margin: 1.75rem 0;
  overflow: hidden;
}

/* chrome bar */
.langswitch .ls-chrome { display: flex; align-items: center; gap: 11px; padding: 11px 15px; border-bottom: 1px solid var(--ls-border); }
.langswitch .ls-dots { display: flex; gap: 6px; }
.langswitch .ls-dots i { width: 11px; height: 11px; border-radius: 50%; display: inline-block; background: var(--ls-border-strong); }
.langswitch .ls-dots i:nth-child(1) { background: #FF5F56; }
.langswitch .ls-dots i:nth-child(2) { background: #FFBD2E; }
.langswitch .ls-dots i:nth-child(3) { background: #27C93F; }
.langswitch .ls-file { font-size: 12px; color: var(--ls-muted); }
.langswitch .ls-copy { margin-left: auto; font-family: var(--ls-mono); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ls-muted); background: transparent; border: 1px solid var(--ls-border-strong); padding: 5px 11px; cursor: pointer; border-radius: 0; transition: color 0.15s, border-color 0.12s, background 0.12s; }
.langswitch .ls-copy:hover { color: var(--ls-amber); border-color: var(--ls-amber); }
.langswitch .ls-copy:active { transform: translateY(1px); }
.langswitch .ls-copy:focus-visible { outline: 2px solid var(--ls-amber); outline-offset: 2px; }

/* tab row */
.langswitch .ls-tabs { display: flex; align-items: center; padding: 0 8px; border-bottom: 1px solid var(--ls-border); }
.langswitch .ls-tab { display: inline-flex; align-items: center; font-family: var(--ls-mono); font-size: 12px; text-transform: uppercase; letter-spacing: 0.07em; padding: 10px 12px; background: transparent; border: none; border-bottom: 2px solid transparent; color: var(--ls-muted); cursor: pointer; white-space: nowrap; transition: color 0.15s, border-color 0.12s; }
.langswitch .ls-tab:hover { color: var(--ls-text); }
.langswitch .ls-tab.is-active { color: var(--ls-amber); border-bottom-color: var(--ls-amber); }
.langswitch .ls-tab:focus-visible { outline: 2px solid var(--ls-amber); outline-offset: -2px; }
.langswitch .ls-tabdot { width: 5px; height: 5px; border-radius: 50%; background: var(--ls-amber); margin-right: 7px; display: inline-block; flex-shrink: 0; }

/* overflow "+N" menu */
.langswitch .ls-overflow { position: relative; margin-left: auto; }
.langswitch .ls-more { font-family: var(--ls-mono); font-size: 12px; color: var(--ls-muted); background: transparent; border: none; padding: 10px; cursor: pointer; white-space: nowrap; }
.langswitch .ls-more:hover, .langswitch .ls-more.is-active { color: var(--ls-amber); }
.langswitch .ls-more:focus-visible { outline: 2px solid var(--ls-amber); outline-offset: -2px; }
.langswitch .ls-menu { position: absolute; right: 0; top: calc(100% + 4px); min-width: 170px; z-index: 7; background: var(--ls-surface-2); border: 1px solid var(--ls-border-strong); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45); }
.langswitch .ls-menuitem { display: flex; align-items: center; gap: 9px; width: 100%; text-align: left; font-family: var(--ls-mono); font-size: 12.5px; padding: 9px 12px; background: transparent; border: none; color: var(--ls-text); cursor: pointer; }
.langswitch .ls-menuitem:hover, .langswitch .ls-menuitem.is-active { background: var(--ls-wash); color: var(--ls-amber); }

/* smart-default hint */
.langswitch .ls-hint { display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-bottom: 1px solid var(--ls-border); background: var(--ls-wash); font-size: 11px; color: var(--ls-muted); }
.langswitch .ls-hint strong { color: var(--ls-amber); font-weight: 700; }
.langswitch .ls-hintdot { width: 5px; height: 5px; border-radius: 50%; background: var(--ls-amber); flex-shrink: 0; display: inline-block; }

/* code panels — inner .highlight blocks from Hugo/Chroma.
   Strip the theme's .prose pre border/margin/background (the container supplies them);
   inherit theme padding + font sizing so switcher code matches surrounding code. */
.langswitch .ls-panels { padding: 0; }
.langswitch .ls-panels .highlight { margin: 0; }
.langswitch .ls-panels .highlight[hidden] { display: none; }
.langswitch .ls-panels .highlight pre { margin: 0; border: 0; border-left: 0; border-radius: 0; background: transparent; }

@media (prefers-reduced-motion: reduce) {
  .langswitch * { transition: none !important; }
}
```

- [ ] **Step 3: Create `themes/scryops/assets/js/langswitch.js`**

```javascript
/* langswitch.js — scryops multi-language code switcher (inline edition).
 *
 * One global selected language, shared by every {{< langswitch >}} block on the
 * page and persisted across reloads. Panels are the inner code blocks Hugo/Chroma
 * rendered (.highlight); their language comes from each <code data-lang>, and the
 * tab label + filename come from window.scryLangMeta (data/langmeta.yaml).
 *   - top-5 popular languages as tabs, the rest behind a "+N" overflow menu
 *   - the active language is promoted into the row if it lives in the overflow
 *   - selection resolved as: saved choice -> ?lang= -> host hook -> block default
 *   - first-load hint shows on the FIRST switcher only, until the first pick
 *
 * No dependencies. Highlighting is done server-side by Hugo/Chroma.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "scry:lang";
  // Popularity order -> which 5 are tabs vs. overflow. Keys are fence languages.
  var POPULAR = ["python", "javascript", "go", "java", "csharp", "rust", "ruby"];
  var VISIBLE_MAX = 5;
  var META = window.scryLangMeta || {};
  var ALIASES = { cs: "csharp", "c#": "csharp", js: "javascript", node: "javascript", golang: "go", py: "python", yml: "yaml", rb: "ruby" };

  var blocks = [];
  var current = null;   // globally selected fence language (or null before resolve)
  var explicit = false; // true once a user/saved choice exists

  function norm(lang) { lang = (lang || "").toLowerCase(); return ALIASES[lang] || lang; }
  function label(lang) { return (META[lang] && META[lang].label) || (lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : lang); }
  function file(lang) { return (META[lang] && META[lang].file) || ""; }

  /* ---- selection resolution ---- */
  function detect() {
    try { var saved = localStorage.getItem(STORAGE_KEY); if (saved) return { lang: norm(saved), explicit: true }; } catch (e) {}
    var qp = null;
    try { qp = new URLSearchParams(location.search).get("lang"); } catch (e) {}
    if (qp) return { lang: norm(qp), explicit: false };
    if (typeof window.scryDetectLang === "function") {
      try { var d = window.scryDetectLang(); if (d) return { lang: norm(d), explicit: false }; } catch (e) {}
    }
    return { lang: null, explicit: false };
  }
  function save(lang) { try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {} }

  function orderFor(langs) {
    var pop = POPULAR.filter(function (l) { return langs.indexOf(l) !== -1; });
    langs.forEach(function (l) { if (pop.indexOf(l) === -1) pop.push(l); });
    return pop;
  }
  function activeFor(b) {
    var ordered = orderFor(b.langs);
    if (current && b.langs.indexOf(current) !== -1) return current;
    if (b.defaultLang && b.langs.indexOf(b.defaultLang) !== -1) return b.defaultLang;
    return ordered[0];
  }
  function partition(ordered, active) {
    var visible = ordered.slice(0, VISIBLE_MAX);
    if (visible.indexOf(active) === -1 && ordered.indexOf(active) !== -1) {
      visible = ordered.slice(0, VISIBLE_MAX - 1).concat([active]);
    }
    var overflow = ordered.filter(function (l) { return visible.indexOf(l) === -1; });
    return { visible: visible, overflow: overflow };
  }

  /* ---- global state ---- */
  function choose(lang) {
    explicit = true; current = lang; save(lang);
    blocks.forEach(render);
    window.dispatchEvent(new CustomEvent("scry:langchange", { detail: { lang: lang } }));
  }

  /* ---- rendering ---- */
  function makeTab(b, lang, active) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ls-tab" + (lang === active ? " is-active" : "");
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", lang === active ? "true" : "false");
    btn.dataset.lang = lang;
    if (lang === b.defaultLang) { var dot = document.createElement("i"); dot.className = "ls-tabdot"; dot.setAttribute("aria-hidden", "true"); btn.appendChild(dot); }
    btn.appendChild(document.createTextNode(label(lang)));
    btn.addEventListener("click", function () { choose(lang); });
    return btn;
  }
  function makeOverflow(b, overflow, active) {
    var wrap = document.createElement("div"); wrap.className = "ls-overflow";
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "ls-more" + (overflow.indexOf(active) !== -1 ? " is-active" : "");
    toggle.setAttribute("aria-haspopup", "true"); toggle.setAttribute("aria-expanded", "false");
    toggle.textContent = "+" + overflow.length + " ▾";
    var menu = document.createElement("div"); menu.className = "ls-menu"; menu.hidden = true;
    overflow.forEach(function (lang) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "ls-menuitem" + (lang === active ? " is-active" : "");
      item.setAttribute("role", "tab");
      item.setAttribute("aria-selected", lang === active ? "true" : "false");
      item.dataset.lang = lang;
      if (lang === b.defaultLang) { var d = document.createElement("i"); d.className = "ls-tabdot"; d.setAttribute("aria-hidden", "true"); item.appendChild(d); }
      item.appendChild(document.createTextNode(label(lang)));
      item.addEventListener("click", function () { closeMenus(); choose(lang); });
      menu.appendChild(item);
    });
    function open(state) { menu.hidden = !state; toggle.setAttribute("aria-expanded", state ? "true" : "false"); toggle.classList.toggle("is-open", state); }
    toggle.addEventListener("click", function (e) { e.stopPropagation(); var willOpen = menu.hidden; closeMenus(); open(willOpen); });
    wrap.appendChild(toggle); wrap.appendChild(menu);
    return wrap;
  }
  function closeMenus() {
    document.querySelectorAll(".langswitch .ls-menu").forEach(function (m) { m.hidden = true; });
    document.querySelectorAll(".langswitch .ls-more").forEach(function (t) { t.setAttribute("aria-expanded", "false"); t.classList.remove("is-open"); });
  }
  function render(b) {
    var active = activeFor(b);
    var ordered = orderFor(b.langs);
    var part = partition(ordered, active);
    b.langs.forEach(function (l) { b.panels[l].hidden = (l !== active); });
    if (b.fileEl) b.fileEl.textContent = file(active);
    b.tabbar.innerHTML = "";
    part.visible.forEach(function (l) { b.tabbar.appendChild(makeTab(b, l, active)); });
    if (part.overflow.length) { b.tabbar.appendChild(makeOverflow(b, part.overflow, active)); }
    if (b.hintEl) {
      var isDefault = active === (b.defaultLang || ordered[0]);
      b.hintEl.hidden = explicit || !isDefault || b !== blocks[0]; // first switcher only
      if (b.hintLabelEl) b.hintLabelEl.textContent = label(active);
    }
  }

  /* ---- init ---- */
  function initBlock(root) {
    var panels = {};
    var host = root.querySelector("[data-ls-panels]") || root;
    host.querySelectorAll(".highlight").forEach(function (h) {
      var code = h.querySelector("code");
      var lang = norm(code && (code.dataset.lang || ""));
      if (!lang) return;
      if (!panels[lang]) panels[lang] = h; // first block per language wins
    });
    var langs = Object.keys(panels);
    if (!langs.length) return;
    var b = {
      root: root, panels: panels, langs: langs,
      tabbar: root.querySelector("[data-ls-tabs]"),
      fileEl: root.querySelector("[data-ls-file]"),
      copyEl: root.querySelector("[data-ls-copy]"),
      hintEl: root.querySelector("[data-ls-hint]"),
      hintLabelEl: root.querySelector("[data-ls-hint-label]"),
      defaultLang: norm(root.dataset.default || "") || null,
    };
    b.tabbar.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var tabs = [].slice.call(b.tabbar.querySelectorAll(".ls-tab"));
      var i = tabs.indexOf(document.activeElement);
      if (i === -1) return;
      e.preventDefault();
      var next = e.key === "ArrowRight" ? (i + 1) % tabs.length : (i - 1 + tabs.length) % tabs.length;
      tabs[next].focus(); choose(tabs[next].dataset.lang);
    });
    if (b.copyEl) {
      b.copyEl.addEventListener("click", function () {
        var active = activeFor(b);
        var pre = b.panels[active] && b.panels[active].querySelector("pre");
        var text = pre ? pre.innerText : "";
        if (navigator.clipboard) navigator.clipboard.writeText(text);
        b.copyEl.textContent = "Copied";
        clearTimeout(b._ct);
        b._ct = setTimeout(function () { b.copyEl.textContent = "Copy"; }, 1500);
      });
    }
    blocks.push(b);
  }

  function boot() {
    var roots = document.querySelectorAll("[data-langswitch]");
    if (!roots.length) return;
    roots.forEach(initBlock);
    if (!blocks.length) return;
    var res = detect();
    explicit = res.explicit; current = res.lang;
    blocks.forEach(render);
    document.addEventListener("click", closeMenus);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeMenus(); });
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); } else { boot(); }
})();
```

- [ ] **Step 4: Create `themes/scryops/layouts/shortcodes/langswitch.html`**

```go-html-template
{{- /*
  langswitch — multi-language code switcher for scryops (inline edition).
  Usage (paired; write one fenced code block per language inside):
    {{< langswitch >}}
    ```python
    ...
    ```
    ```go
    ...
    ```
    {{< /langswitch >}}
  Optional first-load default: {{< langswitch default="go" >}}

  One global language choice, shared across every block on the page and persisted
  across reloads (assets/js/langswitch.js). Highlighting is server-side Chroma using
  the theme's global .chroma palette. Assets + langmeta inject once per page.
*/ -}}
{{- $default := .Get "default" | default "python" -}}
{{- $store := .Page.Store -}}
{{- if not ($store.Get "lsAssets") -}}
  {{- $store.Set "lsAssets" true -}}
  {{- with resources.Get "css/langswitch.css" }}<link rel="stylesheet" href="{{ (. | minify | fingerprint).RelPermalink }}">{{ end -}}
  {{- with resources.Get "js/langswitch.js" }}<script src="{{ (. | minify | fingerprint).RelPermalink }}" defer></script>{{ end -}}
  {{- with .Site.Data.langmeta }}<script>window.scryLangMeta={{ . | jsonify }};</script>{{ end -}}
{{- end -}}
<div class="langswitch" data-langswitch data-default="{{ $default }}">
  <div class="ls-chrome">
    <span class="ls-dots" aria-hidden="true"><i></i><i></i><i></i></span>
    <span class="ls-file" data-ls-file></span>
    <button class="ls-copy" type="button" data-ls-copy aria-live="polite">Copy</button>
  </div>
  <div class="ls-tabs" role="tablist" aria-label="Choose a language" data-ls-tabs></div>
  <div class="ls-hint" data-ls-hint hidden>
    <i class="ls-hintdot" aria-hidden="true"></i>
    <span>Showing <strong data-ls-hint-label></strong> — pick your language and we'll remember it.</span>
  </div>
  <div class="ls-panels" data-ls-panels>
{{ .Inner | markdownify }}
  </div>
</div>
```

- [ ] **Step 5: Migrate the run-jaeger group (smoke test)**

In `content/howtos/run-jaeger-locally-with-opentelemetry.md`, change the single group's open/close tags. Inner fences stay unchanged.

Replace `{{< codetabs >}}` → `{{< langswitch >}}` and `{{< /codetabs >}}` → `{{< /langswitch >}}`.

- [ ] **Step 6: Build and confirm no errors**

Run: `cd "/Users/jonhdoe/Repository/scryops-site" && hugo --gc --minify --logLevel info 2>&1 | tail -20`
Expected: ends with a `Total in …` summary and **no `ERROR`** lines (in particular no "shortcode "langswitch" not found" or template parse error). Confirm the page exists: `test -f public/howtos/run-jaeger-locally-with-opentelemetry/index.html && echo OK`.

- [ ] **Step 7: Browser smoke test**

Start the dev server in the background (`hugo server -D --port 1313`) and drive it with the preview/Playwright tools. Navigate to `http://localhost:1313/howtos/run-jaeger-locally-with-opentelemetry/`. Verify:
- The switcher renders: a chrome bar with filename (`main.go`/`app.py`/`Program.cs` depending on active), a tab row showing **Python / Go / .NET**, and exactly one visible code block.
- The first-load hint reads "Showing Python — pick your language and we'll remember it." (no "detected from your project").
- Clicking **Go** shows the Go code; filename switches to `main.go`.
- In the browser console, `localStorage.getItem('scry:lang')` returns `"go"` after the click.
- Inner code token colors match a normal (non-switcher) code block elsewhere on the page (same Monokai-ish palette).

If any check fails, fix the relevant file and re-run Steps 6–7 before committing.

- [ ] **Step 8: Commit**

```bash
cd "/Users/jonhdoe/Repository/scryops-site"
git add themes/scryops/data/langmeta.yaml \
        themes/scryops/assets/css/langswitch.css \
        themes/scryops/assets/js/langswitch.js \
        themes/scryops/layouts/shortcodes/langswitch.html \
        content/howtos/run-jaeger-locally-with-opentelemetry.md
git commit -m "feat(theme): inline langswitch code switcher; migrate run-jaeger

Adds a paired {{< langswitch >}} shortcode with one global, persisted
language choice across all blocks on a page (top-5 + overflow, smart
default, copy, ARIA/keyboard). Reuses the theme Chroma palette. Smoke-
tested on the run-jaeger how-to.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Migrate the remaining 9 groups

Mechanical tag rename across the three remaining files. Inner fences untouched.

**Files:**
- Modify: `content/howtos/instrument-python-service-opentelemetry.md` (4 groups)
- Modify: `content/howtos/wire-trace-ids-into-logs.md` (2 groups)
- Modify: `content/guides/high-throughput-logging.md` (3 groups)

**Interfaces:**
- Consumes: the `{{< langswitch >}}` shortcode from Task 1. No new interfaces.

- [ ] **Step 1: Rename tags in all three files**

In each file, replace every `{{< codetabs >}}` → `{{< langswitch >}}` and every `{{< /codetabs >}}` → `{{< /langswitch >}}` (use replace-all per file). Counts to expect: instrument-python = 4 open / 4 close; wire-trace-ids = 2 / 2; high-throughput-logging = 3 / 3.

- [ ] **Step 2: Confirm no `codetabs` references remain in content**

Run: `cd "/Users/jonhdoe/Repository/scryops-site" && grep -rn "codetabs" content/ ; echo "exit: $?"`
Expected: no matches, `exit: 1` (grep found nothing).

- [ ] **Step 3: Build**

Run: `cd "/Users/jonhdoe/Repository/scryops-site" && hugo --gc --minify 2>&1 | tail -8`
Expected: no `ERROR` lines; clean `Total in …` summary.

- [ ] **Step 4: Browser spot-check the 4-switcher page**

With `hugo server` running, navigate to `http://localhost:1313/howtos/instrument-python-service-opentelemetry/`. Verify:
- All 4 switchers render with Python/Go/.NET tabs.
- The onboarding hint appears on the **first switcher only** (not all four).
- Picking **.NET** on any one switcher flips **all four** to .NET (filename `Program.cs`); reload keeps .NET selected.

- [ ] **Step 5: Commit**

```bash
cd "/Users/jonhdoe/Repository/scryops-site"
git add content/howtos/instrument-python-service-opentelemetry.md \
        content/howtos/wire-trace-ids-into-logs.md \
        content/guides/high-throughput-logging.md
git commit -m "content: migrate remaining codetabs groups to langswitch

instrument-python (4), wire-trace-ids (2), high-throughput-logging (3).
Tag rename only; code unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Retire `codetabs`

**Files:**
- Delete: `themes/scryops/layouts/shortcodes/codetabs.html`

**Interfaces:** none. (All consumers migrated in Tasks 1–2.)

- [ ] **Step 1: Delete the shortcode**

Run: `cd "/Users/jonhdoe/Repository/scryops-site" && git rm themes/scryops/layouts/shortcodes/codetabs.html`

- [ ] **Step 2: Confirm nothing references it**

Run: `cd "/Users/jonhdoe/Repository/scryops-site" && grep -rn "codetabs" content/ themes/ layouts/ 2>/dev/null ; echo "exit: $?"`
Expected: no matches, `exit: 1`.

- [ ] **Step 3: Build to prove no usage broke**

Run: `cd "/Users/jonhdoe/Repository/scryops-site" && hugo --gc --minify 2>&1 | tail -8`
Expected: no `ERROR` lines.

- [ ] **Step 4: Commit**

```bash
cd "/Users/jonhdoe/Repository/scryops-site"
git commit -m "refactor(theme): remove codetabs shortcode (replaced by langswitch)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Cross-page verification + accessibility + polish

Final behavioral pass across pages and a11y. Commit only if a fix is needed.

**Files:**
- Modify (only if a defect is found): `themes/scryops/assets/css/langswitch.css` or `themes/scryops/assets/js/langswitch.js`

**Interfaces:** none.

- [ ] **Step 1: Persistence across pages**

With `hugo server` running and storage cleared, pick **Go** on `/howtos/run-jaeger-locally-with-opentelemetry/`, then navigate to `/howtos/wire-trace-ids-into-logs/` and `/guides/high-throughput-logging/`. Expected: Go is pre-selected on both without re-picking.

- [ ] **Step 2: Deep link**

In a context with cleared `localStorage`, open `http://localhost:1313/howtos/wire-trace-ids-into-logs/?lang=csharp`. Expected: .NET is the active tab on first paint.

- [ ] **Step 3: Keyboard + copy + reduced-motion**

- Focus a tab; press ←/→: focus and selection move across tabs; all blocks follow.
- Click **Copy**; the button shows "Copied"; clipboard holds the active block's code.
- Confirm CSS contains the `@media (prefers-reduced-motion: reduce)` block disabling transitions.

- [ ] **Step 4: Accessibility assertions**

In the browser, verify the tab row has `role="tablist"`; tabs have `role="tab"` and `aria-selected` toggling true/false on selection; the overflow toggle (if present) has `aria-haspopup`/`aria-expanded`. (For the migrated 3-language content no overflow appears — confirm by adding `?lang=` is irrelevant; overflow only exists with >5 languages.)

- [ ] **Step 5: Palette parity**

On any migrated page, confirm switcher code and a regular fenced code block share identical token colors (keywords, strings, comments). If they differ, the theme `.chroma` palette is being overridden — fix the offending rule in `langswitch.css` (it must not set token colors).

- [ ] **Step 6: Commit any fixes**

Only if Steps 1–5 required edits:
```bash
cd "/Users/jonhdoe/Repository/scryops-site"
git add themes/scryops/assets/
git commit -m "fix(theme): langswitch verification polish

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7: Stop the dev server**

Stop the background `hugo server` process started during verification.

---

## Self-Review

**Spec coverage:**
- Replace codetabs → Tasks 1–3 (build, migrate all 10, delete). ✓
- Inline authoring model (no codesamples.yaml) → shortcode uses `.Inner | markdownify` (Task 1 Step 4). ✓
- Global persisted choice + overflow + smart default + copy + a11y → `langswitch.js` (Task 1 Step 3). ✓
- Chroma reconciliation (drop chroma-scryops.css; one palette) → Global Constraints + Task 1 Step 2 CSS + Task 4 Step 5. ✓
- langmeta keyed by fence language → Task 1 Step 1. ✓
- Honest hint copy (no "detected") → Task 1 Step 4 markup + Step 7 check. ✓
- `?lang=` deep link → `detect()` + Task 4 Step 2. ✓
- All-in-theme placement → File Structure. ✓
- Verification = build + browser → each task's gate. ✓

**Placeholder scan:** No TBD/TODO; all code blocks complete; commands have expected output. ✓

**Type/contract consistency:** DOM hooks (`data-langswitch`, `data-ls-tabs`, `data-ls-file`, `data-ls-copy`, `data-ls-hint`, `data-ls-hint-label`, `data-ls-panels`, `data-default`) match between `langswitch.html` (Task 1 Step 4) and `langswitch.js` (Task 1 Step 3). `window.scryLangMeta` shape (`{lang:{label,file}}`) matches between shortcode `jsonify` and JS `META[lang].label/.file`. `POPULAR` fence keys match `langmeta.yaml` keys. ✓
