# DS Reconciliation Phase 1 — Token Palette · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the live theme's dark + light color palette (plus two line-heights and two radius tokens) to the ScryOps design system's warm/de-neon Jul-2026 values, in a single CSS file.

**Architecture:** Values-only edits to the `:root` (dark) and `html.light` token blocks of `themes/scryops/assets/css/telemetry.css`. Token *names* are unchanged, so every rule keeps resolving and the theme's bridge-alias block cascades the new palette to all components; the 43 pre-rendered Mermaid SVGs and `obs-*` figures re-theme for free via `var(--node-fill/--node-stroke/--edge/--nlab)`. `html.calm` is not touched.

**Tech Stack:** Hugo 0.145 (extended), CSS custom properties, Hugo Pipes (fingerprints `telemetry.css`).

## Global Constraints

- **Single file:** every edit is in `themes/scryops/assets/css/telemetry.css`. No other file changes.
- **Values only, never names:** change token *values*; never rename a token or alter a selector. (BEM renames are a later phase.)
- **`html.calm` is untouched** — it already matches the design system.
- **Authoritative source of every target value:** the design system's `tokens/colors.css` at
  `/private/tmp/claude-501/-Users-jonhdoe-Library-Application-Support-Claude-local-agent-mode-sessions-9ac5e0c1-f28c-4cee-a200-9ce5887c8d75-b3f4314e-2b50-4402-83ef-551b516ea675-local-73810ae7-22ea-480c-b8bb-6ddb9dc9c458-outputs/94093fd2-2ffc-43d6-bf99-f9969cf53e16/scratchpad/ds-handoff/scryops-design-system/project/tokens/colors.css`
  (`:root` = dark, `html.light` = light). After editing, cross-check your result against it.
- **Build tool:** verify with `~/bin/hugo` (0.145, the CI version), NOT the 0.159 on PATH.
- **Building atop uncommitted WIP:** the working tree has an unrelated in-flight a11y/polish pass. Touch ONLY the token lines in this plan; leave every other modified file (aria-labels, prefs.js, etc.) alone. Do not `git add -A` — stage only `telemetry.css`.
- **No AI commit attribution** — no `Co-Authored-By`, no tool footer.
- **SPEC DEVIATION (flagged, approved at handoff):** this plan reconciles the always-dark **code-well** tokens (`--code-bg/-text/-bd/-hi/-muted/-green/-cyan`) too — the drift audit wrongly reported them as matching, but the design system warmed them. This deviates from the spec's literal "do not change code-well." Included because the design system is source of truth and cool code wells on a warm page would look inconsistent.

---

## Task 1: Dark theme (`:root`) color block

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:10-48`

**Interfaces:**
- Produces: the warm/de-neon dark palette that all dark-theme components + diagrams inherit. No later task depends on exact intermediate values.

- [ ] **Step 1: Replace the dark color block (lines 10-48)**

Replace this exact current block:

```css
  /* ---- color · dark (default) — Telemetry ---- */
  --bg:#0F1617;             /* lifted from #0A0E0F — softer near-black, less austere (body still 13:1) */
  --surface:#151E1F;        /* lifted with --bg to keep card elevation above the page */
  --border:#1E2C2E;
  --heading:#EAF0EE;
  --text:#D6DBD9;
  --muted:#7FA6A0;
  --green:#3DDC84;          /* healthy / values / INFO */
  --cyan:#5BD8E8;           /* identifiers / links / edges */
  --link:#5BD8E8;
  --warn:#E0C24A;
  --danger:#FF6B6B;
  --violet:#9D7CF0;         /* OpenTelemetry topic accent */

  /* inline code chip */
  --ic-bg:#182322; --ic-text:#5BD8E8; --ic-bd:#1C2A2B;

  /* code well — STAYS DARK in all three themes */
  --code-bg:#0C1213; --code-text:#C8D2CF; --code-bd:#182426;
  /* readout constants — used ON the always-dark code/terminal wells,
     so they must NOT flip with theme (light/calm leave these alone). */
  --code-hi:#EAF0EE; --code-muted:#7E9A8E; --code-green:#3DDC84; --code-cyan:#5BD8E8;
  /* permacomputing — living-green resource-awareness accent (well only) */
  --eco:#7FB069; --eco-bright:#A8D88A;

  /* figures */
  --fig-bg:#121A1B;
  --fig-grid:linear-gradient(rgba(127,166,160,.07) 1px,transparent 1px),
             linear-gradient(90deg,rgba(127,166,160,.07) 1px,transparent 1px);
  --fig-bd:#1E2C2E;
  --node-fill:#10191A; --node-stroke:#2BAE76; --edge:#5BD8E8; --nlab:#EAF0EE;

  /* callouts */
  --info-bg:rgba(61,220,132,.07); --info-bd:#3DDC84; --info-lb:#5FE39A;
  --warn-bg:rgba(224,194,74,.08); --warn-bd:#E0C24A; --warn-lb:#E8CE66;
  --dgr-bg:rgba(255,107,107,.08); --dgr-bd:#FF6B6B; --dgr-lb:#FF8585;

  /* tables */
  --th:#1A2425; --tborder:#182426;
```

with this exact new block (design-system warm/de-neon values):

```css
  /* ---- color · dark (default) — Telemetry, warm/de-neon (DS Jul-2026) ---- */
  --bg:#141210;             /* warm charcoal — softened near-black (body still ~12.6:1) */
  --surface:#1C1915;        /* card elevation above the page */
  --border:#2B2620;
  --heading:#ECE6D9;
  --text:#D7D0C4;
  --muted:#9B9382;
  --green:#66C892;          /* healthy / values / INFO / brand / CTA (de-neoned) */
  --cyan:#6FC6D1;           /* identifiers / links / edges (softened) */
  --link:#6FC6D1;
  --warn:#DCC061;
  --danger:#F0857A;         /* softer coral — reads as error, not alarm */
  --violet:#A78FE0;         /* OpenTelemetry topic accent */

  /* inline code chip */
  --ic-bg:#1E1A14; --ic-text:#6FC6D1; --ic-bd:#241F18;

  /* code well — STAYS DARK in all three themes */
  --code-bg:#100E0B; --code-text:#CEC8BC; --code-bd:#201C16;
  /* readout constants — used ON the always-dark code/terminal wells,
     so they must NOT flip with theme (light/calm leave these alone). */
  --code-hi:#ECE6D9; --code-muted:#8E877A; --code-green:#66C892; --code-cyan:#6FC6D1;
  /* permacomputing — living-green resource-awareness accent (well only) */
  --eco:#7FB069; --eco-bright:#A8D88A;

  /* figures */
  --fig-bg:#17130E;
  --fig-grid:linear-gradient(rgba(155,147,130,.06) 1px,transparent 1px),
             linear-gradient(90deg,rgba(155,147,130,.06) 1px,transparent 1px);
  --fig-bd:#2B2620;
  --node-fill:#16120C; --node-stroke:#4FA77C; --edge:#6FC6D1; --nlab:#ECE6D9;

  /* callouts */
  --info-bg:rgba(102,200,146,.07); --info-bd:#66C892; --info-lb:#8AD4A8;
  --warn-bg:rgba(220,192,97,.09); --warn-bd:#DCC061; --warn-lb:#E6CE7A;
  --dgr-bg:rgba(240,133,122,.09); --dgr-bd:#F0857A; --dgr-lb:#F5A096;

  /* tables */
  --th:#211D17; --tborder:#221E18;
```

Note: `--eco` / `--eco-bright` are unchanged (they already match the design system); they stay in the block as-is.

- [ ] **Step 2: Cross-check values against the design system**

Run (compares your edited dark tokens to the DS source; expects no differences in the color values):
```bash
cd /Users/jonhdoe/Repository/scryops-site
for t in "bg:#141210" "green:#66C892" "cyan:#6FC6D1" "danger:#F0857A" "violet:#A78FE0" "node-stroke:#4FA77C" "edge:#6FC6D1" "code-bg:#100E0B" "code-green:#66C892" "th:#211D17"; do
  grep -q -- "--${t}" themes/scryops/assets/css/telemetry.css && echo "OK  --$t" || echo "MISS --$t"
done
```
Expected: 10 `OK` lines, zero `MISS`.

- [ ] **Step 3: Confirm the old neon values are gone from `:root`**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -nE -- '--(bg:#0F1617|green:#3DDC84|cyan:#5BD8E8|danger:#FF6B6B|node-stroke:#2BAE76)' themes/scryops/assets/css/telemetry.css || echo "clean: no stale dark values"
```
Expected: `clean: no stale dark values` (these old values must not remain; note `--code-green`/`--code-cyan` also changed, so `#3DDC84`/`#5BD8E8` should now appear ZERO times in the file — the light block never used them).

- [ ] **Step 4: Build with Hugo 0.145**

Run: `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-t1 2>&1 | tail -4`
Expected: `0 errors`.

- [ ] **Step 5: Commit (stage only telemetry.css)**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css
git commit -m "feat(ds-tokens): reconcile dark palette to design system (warm/de-neon)"
```
(The pre-commit hook runs verify_visuals.py + tag checks; expected to pass. Do NOT `git add -A` — other WIP files must stay unstaged.)

---

## Task 2: Light theme (`html.light`) color block

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:98-125`

**Interfaces:**
- Consumes: nothing from Task 1 (independent block).
- Produces: the warm-cream light palette.

- [ ] **Step 1: Replace the drifted light tokens (lines 98-125)**

Replace this exact current block:

```css
  --bg:#F4F6F5;
  --surface:#FFFFFF;
  --border:#DEE5E2;
  --heading:#10201A;
  --text:#18201E;
  --muted:#5A6863;
  --green:#157A45;
  --cyan:#0E7E91;
  --link:#0B6C7D;   /* AA: 5.6:1 on --bg (was #0E7E91 = 4.39:1, below AA) */
  --warn:#8A6A14;
  --danger:#C2382F;
  --violet:#6B4FC4;

  --ic-bg:#E6EDEA; --ic-text:#0E7E91; --ic-bd:#D2DDD8;

  /* code well intentionally NOT overridden — stays dark */

  --fig-bg:#FFFFFF;
  --fig-grid:linear-gradient(#E6EDEA 1px,transparent 1px),
             linear-gradient(90deg,#E6EDEA 1px,transparent 1px);
  --fig-bd:#DEE5E2;
  --node-fill:#EAF1ED; --node-stroke:#1E8F52; --edge:#0E7E91; --nlab:#18201E;

  --info-bg:#E7F2EB; --info-bd:#157A45; --info-lb:#157A45;
  --warn-bg:#FBF1DA; --warn-bd:#B08A1E; --warn-lb:#8A6A14;
  --dgr-bg:#FBE9E7; --dgr-bd:#C2382F; --dgr-lb:#A8281F;

  --th:#EEF2F0; --tborder:#DEE5E2;
```

with this exact new block (warm-cream; accents/callouts already matched and are preserved):

```css
  --bg:#F6F3EC;
  --surface:#FFFDF7;
  --border:#E6DFD2;
  --heading:#1E1811;
  --text:#2C261E;
  --muted:#6F6556;
  --green:#157A45;
  --cyan:#0E7E91;
  --link:#0B6C7D;   /* AA: ~4.5:1 on --bg */
  --warn:#8A6A14;
  --danger:#C2382F;
  --violet:#6B4FC4;

  --ic-bg:#EDE7DB; --ic-text:#0E7E91; --ic-bd:#DED6C7;

  /* code well intentionally NOT overridden — stays dark */

  --fig-bg:#FFFDF7;
  --fig-grid:linear-gradient(#EDE7DB 1px,transparent 1px),
             linear-gradient(90deg,#EDE7DB 1px,transparent 1px);
  --fig-bd:#E6DFD2;
  --node-fill:#F0EBE0; --node-stroke:#1E8F52; --edge:#0E7E91; --nlab:#2C261E;

  --info-bg:#E9F0E4; --info-bd:#157A45; --info-lb:#157A45;
  --warn-bg:#FBF1DA; --warn-bd:#B08A1E; --warn-lb:#8A6A14;
  --dgr-bg:#F8E9E4; --dgr-bd:#C2382F; --dgr-lb:#A8281F;

  --th:#EFEAE0; --tborder:#E6DFD2;
```

(Changed: `--bg/--surface/--border/--heading/--text/--muted`, `--ic-bg/-bd`, `--fig-bg/-grid/-bd`, `--node-fill`, `--nlab`, `--info-bg`, `--dgr-bg`, `--th/--tborder`. Unchanged and preserved: the accent colors, `--ic-text`, `--node-stroke`, `--edge`, and the `--warn-*`/`--info-bd/-lb`/`--dgr-bd/-lb` values.)

- [ ] **Step 2: Cross-check + confirm stale values gone**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
for t in "bg:#F6F3EC" "surface:#FFFDF7" "heading:#1E1811" "text:#2C261E" "muted:#6F6556" "node-fill:#F0EBE0" "th:#EFEAE0"; do
  grep -q -- "--${t}" themes/scryops/assets/css/telemetry.css && echo "OK  --$t" || echo "MISS --$t"
done
grep -nE -- '--(bg:#F4F6F5|heading:#10201A|text:#18201E|muted:#5A6863)' themes/scryops/assets/css/telemetry.css || echo "clean: no stale light values"
```
Expected: 7 `OK` lines, then `clean: no stale light values`.

- [ ] **Step 3: Build with Hugo 0.145**

Run: `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-t2 2>&1 | tail -4`
Expected: `0 errors`.

- [ ] **Step 4: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css
git commit -m "feat(ds-tokens): reconcile light palette to design system (warm cream)"
```

---

## Task 3: Line-heights + missing radius tokens

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:64` (line-heights) and `:72` (radius tokens)

**Interfaces:**
- Independent single-line edits.

- [ ] **Step 1: Update the two drifted line-heights (line 64)**

Replace:
```css
  --lh-body:1.7;     --lh-lede:1.68;   --lh-code:1.75;
```
with:
```css
  --lh-body:1.75;    --lh-lede:1.72;   --lh-code:1.75;
```
(`--lh-code` stays `1.75`.)

- [ ] **Step 2: Add the two missing radius tokens (line 72)**

Replace:
```css
  --radius:10px; --radius-sm:6px; --space:8px; --hair:1px;
```
with:
```css
  --radius:10px; --radius-sm:6px; --radius-retro:3px; --radius-pill:999px; --space:8px; --hair:1px;
```
(Additive — no existing rule needs to consume `--radius-retro`/`--radius-pill` in Phase 1; wiring the hardcoded `999px` literals to `var(--radius-pill)` is a later component phase.)

- [ ] **Step 3: Verify + build**

Run:
```bash
cd /Users/jonhdoe/Repository/scryops-site
grep -q -- '--lh-body:1.75' themes/scryops/assets/css/telemetry.css && grep -q -- '--radius-retro:3px' themes/scryops/assets/css/telemetry.css && grep -q -- '--radius-pill:999px' themes/scryops/assets/css/telemetry.css && echo "tokens OK"
~/bin/hugo --buildDrafts --gc --destination /tmp/scryops-t3 2>&1 | tail -4
```
Expected: `tokens OK`, then `0 errors`.

- [ ] **Step 4: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css
git commit -m "feat(ds-tokens): line-heights to 1.75/1.72 + add radius-retro/pill tokens"
```

---

## Task 4: Full verification (dark / light / calm / diagrams / contrast)

No code — acceptance gate. Uses the preview/browser tooling.

**Files:** none.

- [ ] **Step 1: Start a preview server (drafts on, own port)**

The user runs their own `hugo server` on 1313; start a throwaway one on a free port so it isn't disturbed:
Run (background): `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo server --buildDrafts --port 1417 --bind 127.0.0.1`
Wait ~8s, then confirm: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:1417/guides/slos-and-error-budgets/` → `200`.

- [ ] **Step 2: Dark theme computed values**

Drive a browser (Playwright MCP) to `http://localhost:1417/guides/slos-and-error-budgets/`. Evaluate:
```js
() => { const r=document.documentElement; r.classList.remove('light','calm'); const c=getComputedStyle(r);
  return { bg:c.getPropertyValue('--bg').trim(), green:c.getPropertyValue('--green').trim(), edge:c.getPropertyValue('--edge').trim() }; }
```
Expected: `--bg` `#141210`, `--green` `#66C892`, `--edge` `#6FC6D1`.

- [ ] **Step 3: Light + calm checks**

Set `html.light`, read `--bg` → expect `#F6F3EC`. Set `html.calm` (remove light), read `--bg` → expect `#17140E` (UNCHANGED from before Phase 1 — calm regression check). Confirm calm `--green` is `#8FB386` (unchanged).

- [ ] **Step 4: Diagram recolor**

On the same page, sample a pre-rendered Mermaid SVG node/edge computed fill in dark, light, calm (as in the Mermaid Task-7 verification). Expected: dark edge resolves to `#6FC6D1` (new), light edge `#0E7E91`, calm edge `#D6B070` (unchanged). Confirms diagrams re-themed via tokens with no re-render.

- [ ] **Step 5: Contrast (AA)**

In dark and light, compute contrast ratio of `--text` on `--bg` and `--link` on `--bg` (use a WCAG ratio snippet in browser_evaluate). Expected: body text ≥ 7:1 (AAA-ish, dark ~12.6:1 per DS note), link ≥ 4.5:1 (AA) in both themes. Record the numbers.

- [ ] **Step 6: Screenshot proof + footprint**

Screenshot the diagram page in dark and light for visual confirmation of the warm/de-neon shift. Confirm the page's footprint/transfer is essentially unchanged (only ~2 token lines added).

- [ ] **Step 7: Stop the preview server**

`lsof -ti:1417 | xargs kill 2>/dev/null`

- [ ] **Step 8: Finish the branch phase**

Confirm the working tree still shows the unrelated WIP files unstaged and only the 3 Phase-1 commits added. Report the diff summary. (Branch wrap-up / PR is deferred until later reconciliation phases, per the phased plan — do not merge yet.)

---

## Notes for the implementer

- **Order:** Tasks 1–3 are independent single-file edits; do them in order for clean commits, but none depends on another's values.
- **Never `git add -A`** — the working tree carries unrelated uncommitted WIP. Stage only `themes/scryops/assets/css/telemetry.css`.
- **Hugo version:** always `~/bin/hugo` (0.145). A build that works on 0.159 (PATH) may differ on the CI version.
- **The DS `tokens/colors.css` is ground truth** — if any cross-check `MISS`es, fix the value to match that file, not the other way around.
