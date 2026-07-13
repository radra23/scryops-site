# DS Reconciliation Phase 2a — Component Drift · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land five localized component drift fixes (Eyebrow tone, Button states, party-gallery→tokens, QuoteWithAuthor avatar/initials, DataTable→tokens) under current class names, matching the ScryOps design system.

**Architecture:** Small, independent edits to `telemetry.css` and four shortcode/layout templates. No class renames (that's Phase 2b). Each fix is one task with a build + compiled-CSS/markup check; a final task does browser verification across dark/light/calm.

**Tech Stack:** Hugo 0.145 (extended), CSS custom properties, Hugo templates.

## Global Constraints

- **Build/verify with `~/bin/hugo` (0.145)**, NOT the 0.159 on PATH.
- **No class renames** — edit under existing names (`.btn`, `.eyebrow`, `.party-*`, `.quote-*`, comparison-table inline styles).
- **Stage only the files each task names.** The working tree has unrelated uncommitted a11y WIP — never `git add -A`.
- **No AI commit attribution** (no `Co-Authored-By`, no footer).
- Bridge alias `--on-accent` = `var(--bg)` (telemetry.css:84) — exists; use it for the primary button text.
- Reference (design system): `…/scratchpad/ds-handoff/scryops-design-system/project/components/…`.

---

## Task 1: Eyebrow tone (muted default + brand opt-in)

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:322` (delete dead rule), `:517` (recolor + add brand)
- Modify: `themes/scryops/layouts/_default/index.html:6` (hero → brand)

**Note:** line 517's `.eyebrow` currently overrides line 322 for both call sites (same specificity, later wins), so its `margin-bottom:11px` already applies to the hero. Keep the margin on the surviving rule — this preserves current spacing for both the hero and section headers; it does not shift the hero.

- [ ] **Step 1: Delete the dead duplicate rule (line 322)**

Remove this line entirely (it is fully overridden by the line-517 rule):
```css
.eyebrow{font-family:var(--font-code);font-size:var(--fs-label);letter-spacing:.18em;text-transform:uppercase;color:var(--green)}
```

- [ ] **Step 2: Recolor the surviving rule (was line 517) to muted + add brand modifier**

Replace:
```css
.eyebrow{font-family:var(--font-code);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--green);margin-bottom:11px}
```
with:
```css
.eyebrow{font-family:var(--font-code);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-bottom:11px}
.eyebrow.brand{color:var(--green)}
```

- [ ] **Step 3: Brand the homepage hero eyebrow**

In `themes/scryops/layouts/_default/index.html:6`, replace:
```html
    <div class="eyebrow">scrying + ops</div>
```
with:
```html
    <div class="eyebrow brand">scrying + ops</div>
```
(Leave `list.html:9`'s `<div class="eyebrow">section</div>` as plain — it becomes muted.)

- [ ] **Step 4: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -c '\.eyebrow{' themes/scryops/assets/css/telemetry.css   # expect 1 (dup removed)
grep -q '\.eyebrow.brand{color:var(--green)}' themes/scryops/assets/css/telemetry.css && echo "brand rule OK"
grep -q 'class="eyebrow brand"' themes/scryops/layouts/_default/index.html && echo "hero branded OK"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-p2a1 2>&1 | tail -3
```
Expected: `1`, `brand rule OK`, `hero branded OK`, `0 errors`.

- [ ] **Step 5: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css themes/scryops/layouts/_default/index.html
git commit -m "feat(ds-2a): eyebrow muted default + brand opt-in (hero branded)"
```

---

## Task 2: Button interaction states

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:343-345`

- [ ] **Step 1: Replace the three flat `.btn` rules with stateful rules**

Replace:
```css
.btn{font-family:var(--font-code);font-size:13px;border-radius:8px;padding:9px 16px;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--text)}
.btn-primary{background:var(--green);color:#06120C;border-color:var(--green)}
.btn-ghost{border-color:transparent;color:var(--link);text-decoration:underline}
```
with:
```css
.btn{font-family:var(--font-code);font-size:13px;line-height:1;display:inline-flex;align-items:center;justify-content:center;gap:8px;border-radius:8px;padding:9px 16px;min-height:40px;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--text);text-decoration:none;transition:border-color .12s,background .12s,color .12s;white-space:nowrap}
.btn:hover{border-color:var(--cyan);color:var(--heading)}
.btn:active{transform:translateY(1px)}
.btn:focus-visible{outline:2px solid var(--link);outline-offset:2px}
.btn[disabled],.btn[aria-disabled="true"]{opacity:.45;cursor:not-allowed;pointer-events:none}
.btn.sm{font-size:12px;padding:7px 12px;min-height:34px}
.btn-primary{background:var(--green);color:var(--on-accent);border-color:var(--green);font-weight:500}
.btn-primary:hover{background:var(--cyan);border-color:var(--cyan);color:var(--on-accent)}
.btn-ghost{border-color:transparent;color:var(--link);text-decoration:underline;text-underline-offset:3px}
.btn-ghost:hover{color:var(--cyan);background:transparent}
```
(The existing `.landing-cta .btn{text-decoration:none}` at line ~657 becomes redundant but harmless — leave it.)

- [ ] **Step 2: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
for r in '\.btn:hover' '\.btn:active' '\.btn:focus-visible' '\.btn\[disabled\]' '\.btn\.sm' '\.btn-primary:hover' 'color:var(--on-accent)'; do grep -q "$r" themes/scryops/assets/css/telemetry.css && echo "OK $r" || echo "MISS $r"; done
grep -q 'color:#06120C' themes/scryops/assets/css/telemetry.css && echo "STALE #06120C present" || echo "clean: no #06120C"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-p2a2 2>&1 | tail -3
```
Expected: 7 `OK`, `clean: no #06120C`, `0 errors`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css
git commit -m "feat(ds-2a): button hover/active/focus/disabled/sm states + tokenized primary"
```

---

## Task 3: party-gallery chrome → tokens

**Files:**
- Modify: `themes/scryops/layouts/shortcodes/party-gallery.html` (inline `<style>` block)

- [ ] **Step 1: Replace the five chrome-color declarations**

Make these exact substitutions in the `<style>` block (keep every other property, and keep all `var(--ac)`/accent usages untouched):

1. Replace `.party-card{margin:0;background:#161616;border:1px solid #2A2A2A;border-top:3px solid var(--ac);overflow:hidden;display:flex;flex-direction:column;}`
   with `.party-card{margin:0;background:var(--surface);border:1px solid var(--border);border-top:3px solid var(--ac);overflow:hidden;display:flex;flex-direction:column;}`
2. Replace `.party-art{background:#0D0D0D;aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;}`
   with `.party-art{background:var(--bg);aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;}`
3. Replace `.party-ph{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.5rem;width:88%;height:88%;border:2px dashed #2E2E2E;border-radius:3px;color:#5A5A52;}`
   with `.party-ph{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.5rem;width:88%;height:88%;border:2px dashed var(--border);border-radius:3px;color:var(--muted);}`
4. Replace `.party-cls{display:block;font-size:.72rem;color:#A8A8A0;margin-bottom:.55rem;}`
   with `.party-cls{display:block;font-size:.72rem;color:var(--muted);margin-bottom:.55rem;}`
5. Replace `.party-quip{margin:0;font-size:.86rem;line-height:1.55;color:#F0EEE8;}`
   with `.party-quip{margin:0;font-size:.86rem;line-height:1.55;color:var(--text);}`

- [ ] **Step 2: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -nE '#(161616|0D0D0D|2A2A2A|2E2E2E|5A5A52|A8A8A0|F0EEE8)' themes/scryops/layouts/shortcodes/party-gallery.html || echo "clean: chrome tokenized"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-p2a3 2>&1 | tail -3
```
Expected: `clean: chrome tokenized` (the per-character accent hexes in the Go `$party` data at the top remain — that's intended; the grep targets only the chrome hexes, which now must be gone from the `<style>` block), `0 errors`.
Note: if the grep matches a character accent hex that happens to equal one of these (it won't — accents are `#4FD1C5/#F5C542/#E55DC8/#8B6CEF/#D98A2B`), investigate before proceeding.

- [ ] **Step 3: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/layouts/shortcodes/party-gallery.html
git commit -m "feat(ds-2a): party-gallery card chrome reads tokens (themes in light/calm)"
```

---

## Task 4: QuoteWithAuthor pixel avatar + initials

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:639` (avatar size)
- Modify: `themes/scryops/layouts/shortcodes/quote_with_author.html` (initials)

- [ ] **Step 1: Shrink the pixel avatar 64→56**

Replace:
```css
.quote-avatar--pixel{width:64px;height:64px;border-radius:7px;object-fit:contain;background:var(--surface);padding:1px;image-rendering:pixelated;image-rendering:crisp-edges}
```
with:
```css
.quote-avatar--pixel{width:56px;height:56px;border-radius:7px;object-fit:contain;background:var(--surface);padding:1px;image-rendering:pixelated;image-rendering:crisp-edges}
```

- [ ] **Step 2: Word-based initials in the shortcode**

In `themes/scryops/layouts/shortcodes/quote_with_author.html`, replace:
```html
    <div class="quote-avatar-initials">
      {{ if $author }}{{ substr $author 0 2 | upper }}{{ end }}
    </div>
```
with:
```html
    <div class="quote-avatar-initials">
      {{ if $author }}{{ $w := split (trim $author " ") " " }}{{ $ini := substr (index $w 0) 0 1 }}{{ if gt (len $w) 1 }}{{ $ini = printf "%s%s" $ini (substr (index $w 1) 0 1) }}{{ end }}{{ $ini | upper }}{{ end }}
    </div>
```
(First letter of each of the first two words; single-word names yield one letter. "Nostradamhen the Seer" → "NT"; "Cluckoo" → "C".)

- [ ] **Step 3: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -q '\.quote-avatar--pixel{width:56px;height:56px' themes/scryops/assets/css/telemetry.css && echo "avatar 56 OK"
grep -q 'substr $author 0 2' themes/scryops/layouts/shortcodes/quote_with_author.html && echo "STALE initials logic" || echo "initials updated OK"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-p2a4 2>&1 | tail -3
```
Expected: `avatar 56 OK`, `initials updated OK`, `0 errors`.
If any content page uses `{{< quote_with_author author="Two Words" >}}` without an image, spot-check the built page shows `TW`.

- [ ] **Step 4: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css themes/scryops/layouts/shortcodes/quote_with_author.html
git commit -m "feat(ds-2a): quote pixel avatar 56px + word-based initials"
```

---

## Task 5: DataTable inline hex → tokens

**Files:**
- Modify: `themes/scryops/layouts/shortcodes/obs-comparison-table.html:3,46,47`

- [ ] **Step 1: Replace the three inline hex colors**

1. Line 3 (caption): replace `color:#A8A8A0;` with `color:var(--muted);` (within the `<caption ... style="…">`).
2. Line 46 (v1 damage cell): replace `<td class="v1" style="color:#FF5555;">` with `<td class="v1" style="color:var(--danger);">`.
3. Line 47 (v2 prevent cell): replace `<td class="v2" style="color:#30DD50;">` with `<td class="v2" style="color:var(--green);">`.

- [ ] **Step 2: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -nE '#(A8A8A0|FF5555|30DD50)' themes/scryops/layouts/shortcodes/obs-comparison-table.html || echo "clean: table tokenized"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-p2a5 2>&1 | tail -3
```
Expected: `clean: table tokenized`, `0 errors`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/layouts/shortcodes/obs-comparison-table.html
git commit -m "feat(ds-2a): comparison-table cells read semantic tokens"
```

---

## Task 6: Full browser verification (dark / light / calm)

No code — acceptance gate.

**Files:** none.

- [ ] **Step 1: Start throwaway preview (own port)**

Run (background): `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo server --buildDrafts --port 1418 --bind 127.0.0.1`
Wait ~8s; `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:1418/` → `200`.

- [ ] **Step 2: Eyebrow tones (homepage)**

Playwright to `http://localhost:1418/`. Evaluate: hero `.eyebrow.brand` computed `color` = green token (`rgb(102,200,146)` dark); a plain `.eyebrow` (navigate to a section list page, e.g. `/guides/`) computed `color` = muted token. Confirm exactly one `.eyebrow{` rule in the compiled CSS.

- [ ] **Step 3: Button states**

On a page with a CTA button (homepage hero), hover a `.btn` via `element.matches`/forced state or dispatch `mouseover`; confirm the computed border-color moves toward `--cyan`. Confirm `.btn:focus-visible` outline via `.focus()`. Confirm compiled CSS contains the disabled + `.sm` rules.

- [ ] **Step 4: party-gallery themes**

Navigate to a page using `{{< party-gallery >}}` (search content: `grep -rl 'party-gallery' content/`). Sample a `.party-card` computed `background`: dark → `--surface` dark value; set `html.light` → background changes to the light `--surface`. Confirm a `.party-name` accent color is unchanged across themes.

- [ ] **Step 5: QuoteWithAuthor + DataTable**

On a page with `obs-comparison-table` (e.g. an observability-vs-monitoring article), the v1/v2 cells compute to `--danger`/`--green` and shift in light/calm; caption is `--muted`. If a no-image `quote_with_author` with a two-word author exists, confirm two-letter initials and 56px pixel avatar.

- [ ] **Step 6: Screenshot + stop server**

Screenshot homepage in dark + light for the record. Then `lsof -ti:1418 | xargs kill 2>/dev/null`.

- [ ] **Step 7: Confirm scope + report**

`git status --short` shows only the intended committed files changed and the ~37 a11y WIP files still unstaged. Report the 5 commit SHAs. (No merge — later reconciliation phases remain; Phase 2b is the BEM rename.)

---

## Notes for the implementer

- **Order:** Tasks 1–5 are independent; do in order for clean commits.
- **Never `git add -A`** — stage only each task's named files.
- **Hugo:** always `~/bin/hugo` (0.145).
- Each CSS/template edit is verified by compiled-build + grep; Task 6 confirms runtime behavior across themes.
