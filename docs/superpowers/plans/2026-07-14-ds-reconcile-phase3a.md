# DS Reconciliation Phase 3a — Reusable Partials + DataTable a11y · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the footprint badge and subscribe form into reusable Hugo partials (DRY, behavior unchanged), and bring the two DataTable shortcodes to consistent DS structure (`<th scope="row" class="rowhead">` + `.scry-table-wrap` scroll container).

**Architecture:** Two partial extractions (byte-equivalent rendered output; JS untouched) + additive a11y/structure edits to two table shortcodes and one CSS rule. No visual change except a scrollbar on overflow and semantic row headers.

**Tech Stack:** Hugo 0.145 (extended), Hugo partials, CSS.

## Global Constraints

- **Build/verify with `~/bin/hugo` (0.145)**, not the 0.159 on PATH.
- Partials keep existing `.scry-*` classes + `data-*` hooks verbatim — `footprint.js` and the subscribe `<script>` are unchanged.
- **SubscribeForm is single-instance-per-page** (its script drives fixed `id`s) — the homepage keeps one instance; multi-instance id-uniquifying is out of scope.
- DataTable edits are additive (row-header cells + scroll wrapper); no restyle of row labels.
- **Stage only each task's named files.** No AI commit attribution.

---

## Task 1: FootprintBadge partial

**Files:**
- Create: `themes/scryops/layouts/partials/footprint-badge.html`
- Modify: `themes/scryops/layouts/partials/footer.html:6-11`

- [ ] **Step 1: Create the partial**

`themes/scryops/layouts/partials/footprint-badge.html`:
```go-html-template
{{- /* Reusable page-weight + CO₂ badge. Params: budget (bytes, default 122880),
       methodHref (default /colophon/#method). Markup + data-* hooks match what
       footprint.js selects — the JS needs no change. No id attrs → safe to use
       more than once per page. */ -}}
{{- $budget := .budget | default 122880 -}}
{{- $method := .methodHref | default "/colophon/#method" -}}
<div class="scry-fp" data-footprint data-fp-budget="{{ $budget }}">
  <div><span class="scry-fp__pr">scry@ops</span>:<span class="scry-fp__ar">~</span>$ du -h --footprint thispage</div>
  <div><span class="scry-fp__hi" data-fp-size>…</span> transferred · <span class="scry-fp__eco" data-fp-co2>…</span> / visit · <span class="scry-fp__status" data-fp-status>measuring…</span></div>
  <div class="scry-fp__bar"><div class="scry-fp__fill" data-fp-fill></div></div>
  <span class="scry-fp__note" data-fp-note>…</span> · <a class="scry-fp__method" href="{{ $method | relURL }}">method ↗</a>
</div>
```

- [ ] **Step 2: Call the partial from footer.html**

Replace the current badge block in `footer.html` (the comment `{{/* permacomputing · Phase 2 … */}}` through the closing `</div>` of `.scry-fp`) with:
```go-html-template
  {{/* permacomputing · Phase 2 — live page-weight + CO₂ badge, filled by footprint.js */}}
  {{ partial "footprint-badge.html" (dict "budget" 122880) }}
```

- [ ] **Step 3: Verify byte-equivalent output + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-3a1 2>&1 | tail -3
# the footer badge should be identical to before; grep the built footer for the hooks:
grep -o 'data-fp-budget="122880"\|scry-fp__fill\|data-fp-status' /tmp/scryops-3a1/index.html | sort -u
```
Expected: `0 errors`; all three hooks present (`data-fp-budget="122880"`, `scry-fp__fill`, `data-fp-status`).

- [ ] **Step 4: Commit**
```bash
git add themes/scryops/layouts/partials/footprint-badge.html themes/scryops/layouts/partials/footer.html
git commit -m "feat(ds-3a): extract footprint badge into reusable partial"
```

---

## Task 2: SubscribeForm partial

**Files:**
- Create: `themes/scryops/layouts/partials/subscribe-form.html`
- Modify: `themes/scryops/layouts/_default/index.html` (replace the inline subscribe block with a partial call)

**Boundary note (critical):** in `index.html`, the subscribe block is `{{ with .Site.Params.brevo_form_url }} … {{ end }}` (starts at the `<!-- Subscribe … -->` comment, line ~37; the `with`'s `{{ end }}` is line ~112). There is a SECOND, trailing `{{ end }}` (line ~113) that closes the page's `{{ define "main" }}` — it MUST stay. Replace ONLY the `with`-block; leave the final `{{ end }}` intact.

- [ ] **Step 1: Create the partial** — move the exact block verbatim

`themes/scryops/layouts/partials/subscribe-form.html`:
```go-html-template
{{- /* Reusable Brevo subscribe form. Self-gating: renders nothing unless
       Site.Params.brevo_form_url is set. Call with the page context:
       {{ partial "subscribe-form.html" . }}
       NOTE: uses fixed ids (subscribe-form/-email/-btn/-msg) — safe on
       different pages, but do NOT place two instances on the same page. */ -}}
{{ with .Site.Params.brevo_form_url }}
<div class="wrap">
<section class="scry-sub" id="subscribe">
  <h2 class="scry-sub__label">Stay in the loop</h2>
  <p class="scry-sub__desc">New articles, guides, and how-tos — no noise, no cadence commitments.</p>
  <form class="scry-sub__form" id="subscribe-form" novalidate>
    <input type="hidden" name="email_address_check" value="">
    <input type="hidden" name="locale" value="en">
    <label for="subscribe-email" class="sr-only">Email address</label>
    <input class="scry-sub__input" id="subscribe-email" type="email" name="EMAIL" placeholder="you@example.com" required autocomplete="email">
    <button class="scry-sub__btn" id="subscribe-btn" type="submit">Subscribe</button>
  </form>
  <p class="scry-sub__msg" id="subscribe-msg" aria-live="polite" hidden></p>
</section>

<script>
(function () {
  var FORM_URL = {{ . | jsonify | safeJS }};
  var form  = document.getElementById('subscribe-form');
  var input = document.getElementById('subscribe-email');
  var btn   = document.getElementById('subscribe-btn');
  var msg   = document.getElementById('subscribe-msg');

  function setState(state, text) {
    msg.textContent = text;
    msg.hidden = false;
    msg.className = 'scry-sub__msg ' + state;
    if (state === 'loading') {
      btn.disabled = true;
      btn.textContent = 'Subscribing…';
    } else {
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }
    if (state === 'success') {
      form.hidden = true;
    }
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var email = input.value.trim();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setState('error', 'Please enter a valid email address.');
      input.focus();
      return;
    }
    setState('loading', '');
    var params = new URLSearchParams();
    params.append('EMAIL', email);
    params.append('email_address_check', '');
    params.append('locale', 'en');
    params.append('html_type', 'simple');
    // no-cors: sibforms.com doesn't return CORS headers we can read,
    // so we post fire-and-forget and show success optimistically.
    fetch(FORM_URL, {
      method: 'POST',
      mode: 'no-cors',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString()
    })
    .then(function () {
      setState('success', "You're in. New pieces land in your inbox as they ship.");
    })
    .catch(function () {
      setState('error', 'Something went wrong. Check your connection and try again.');
    });
  });
}());
</script>
</div>
{{ end }}
```

- [ ] **Step 2: Replace the inline block in index.html with the partial call**

Delete the inline block (the `<!-- Subscribe … -->` comment through the `with`-block's `{{ end }}`) and put in its place:
```go-html-template
{{ partial "subscribe-form.html" . }}
```
Leave the trailing `{{ end }}` (the `define "main"` close) untouched.

- [ ] **Step 3: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-3a2 2>&1 | tail -3
grep -c 'id="subscribe-form"\|scry-sub__btn\|FORM_URL' /tmp/scryops-3a2/index.html
grep -c 'partial "subscribe-form.html"' themes/scryops/layouts/_default/index.html
```
Expected: `0 errors`; the built homepage still contains the form + script (count ≥ 1 for each hook, assuming `brevo_form_url` is set — if the site param is unset locally the section is absent, which is the correct self-gating behavior; in that case confirm the build is still clean and index.html calls the partial once).

- [ ] **Step 4: Commit**
```bash
git add themes/scryops/layouts/partials/subscribe-form.html themes/scryops/layouts/_default/index.html
git commit -m "feat(ds-3a): extract subscribe form into reusable partial"
```

---

## Task 3: DataTable a11y structure (rowhead + scroll wrap)

**Files:**
- Modify: `themes/scryops/layouts/shortcodes/obs-comparison-table.html`, `themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html`, `themes/scryops/assets/css/telemetry.css`

- [ ] **Step 1: CSS — add the scroll-wrap rule + `.rowhead` hook**

In `telemetry.css`, add the wrap rule immediately after the `.scry-table` block (after line 432):
```css
.scry-table-wrap{overflow-x:auto}
```
And extend the existing row-header selector (line 430) to include `.rowhead` so the class is styled identically to `th[scope="row"]`. Change:
```css
.scry-table td:first-child,.scry-table tbody th[scope="row"]{font-family:var(--font-code);color:var(--muted);font-weight:400;font-size:11px;text-transform:uppercase;letter-spacing:.08em;white-space:nowrap;background:var(--th);text-align:left}
```
to:
```css
.scry-table td:first-child,.scry-table tbody th[scope="row"],.scry-table tbody th.rowhead{font-family:var(--font-code);color:var(--muted);font-weight:400;font-size:11px;text-transform:uppercase;letter-spacing:.08em;white-space:nowrap;background:var(--th);text-align:left}
```

- [ ] **Step 2: obs-comparison-table.html — row-header cells + wrapper**

1. Wrap the table: change the opening `<table class="scry-table" aria-describedby="scry-table-caption">` so it is preceded by `<div class="scry-table-wrap">` and the closing `</table>` is followed by `</div>`. (Add a wrapper div around the whole `<table>…</table>`.)
2. Every body row's FIRST cell is currently a plain `<td>` label (e.g. `<td>Core question</td>`, `<td>Action trigger</td>`, …). Change each row's first `<td>LABEL</td>` to `<th scope="row" class="rowhead">LABEL</th>`. (Only the first cell of each `<tbody>` row — the `.v1`/`.v2` data cells stay `<td>`.)

- [ ] **Step 3: obs-monitoring-shifts.html — swap the wrapper class + add `.rowhead`**

1. Change the bare `<div style="overflow-x:auto">` to `<div class="scry-table-wrap">`.
2. This file already uses `<th scope="row">LABEL</th>` for row labels — add `class="rowhead"`: `<th scope="row" class="rowhead">LABEL</th>` on each.

- [ ] **Step 4: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -c 'scry-table-wrap' themes/scryops/layouts/shortcodes/obs-comparison-table.html themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html
grep -c 'th scope="row" class="rowhead"' themes/scryops/layouts/shortcodes/obs-comparison-table.html themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html
grep -q 'scry-table-wrap{overflow-x:auto}' themes/scryops/assets/css/telemetry.css && echo "wrap css OK"
grep -q '\.scry-table tbody th\.rowhead' themes/scryops/assets/css/telemetry.css && echo "rowhead css OK"
# guard: no bare inline overflow style left, no stray <td> row labels in comparison table
grep -c 'style="overflow-x:auto"' themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-3a3 2>&1 | tail -3
```
Expected: each shortcode shows `scry-table-wrap` = 1; both shortcodes now have `th scope="row" class="rowhead"` (comparison-table = number of body rows, monitoring-shifts = its row count); `wrap css OK`, `rowhead css OK`; `style="overflow-x:auto"` count = 0 in monitoring-shifts; build `0 errors`.

- [ ] **Step 5: Commit**
```bash
git add themes/scryops/layouts/shortcodes/obs-comparison-table.html themes/scryops/layouts/shortcodes/obs-monitoring-shifts.html themes/scryops/assets/css/telemetry.css
git commit -m "feat(ds-3a): DataTable row-header cells + scry-table-wrap scroll container"
```

---

## Task 4: Full verification (browser)

No code — acceptance gate. Start a throwaway server (`~/bin/hugo server --buildDrafts --port 1420`), drive Playwright.

- [ ] **Step 1:** Homepage loads (200). The footprint badge in the footer still fills (`.scry-fp__fill` width set by footprint.js; `[data-fp-size]` shows a KB value) — confirms the partial's data-hooks work. The subscribe section renders (if `brevo_form_url` set) and its submit handler is wired (button present, `#subscribe-msg` exists).
- [ ] **Step 2:** A comparison-table article (e.g. `/articles/what-is-observability-2-and-why-scryops/`) and a monitoring-shifts page: each `.scry-table` is inside a `.scry-table-wrap` (computed `overflow-x: auto` on the wrapper); every body row's first cell is a `<th scope="row" class="rowhead">` (query `.scry-table tbody th[scope="row"]`) and its computed color/background match the pre-3a row-label styling (muted, `--th` bg). Resize narrow (e.g. 380px) and confirm the wrapper scrolls rather than the page.
- [ ] **Step 3:** Subscribe behavior spot-check (if form present): submitting an invalid email shows the `.scry-sub__msg.error` state; a valid one goes to `loading`. (Do not actually submit to Brevo repeatedly — one check.)
- [ ] **Step 4:** Screenshot footer badge + a table in dark + narrow width; stop the server (`lsof -ti:1420 | xargs kill`).
- [ ] **Step 5:** Report the 3 commit SHAs; confirm `git status` clean. (No merge — 3b/3c remain.)

---

## Notes for the implementer

- **Byte-equivalence:** the partials must reproduce the current markup exactly (they're extractions). The footer badge and homepage form should render identically to before — only their source location moved.
- **The trailing `{{ end }}` in index.html** closes `define "main"` — do not delete it when removing the inline subscribe block.
- **Row-header scope:** in comparison-table, only the FIRST cell of each `<tbody>` row becomes `<th scope="row" class="rowhead">`; the `<thead>` `<th scope="col">` cells and the `.v1`/`.v2` data `<td>`s are unchanged.
- Always `~/bin/hugo` (0.145). Stage only each task's named files.
