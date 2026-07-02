# Pre-rendered static-SVG Mermaid diagrams — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the client-side CDN Mermaid runtime with theme-tokenized static inline SVG pre-rendered at build time, so diagram pages ship KB not MB, need zero JS, and invert across dark/light/calm.

**Architecture:** A local Python script (`render-diagrams.py`) shells to `mmdc` (mermaid-cli) to render each `{{< mermaid >}}` block, then a shared Python module rewrites the SVG's baked colors to the site's existing `--node-*`/`--edge`/`--nlab` CSS variables and commits it under `themes/scryops/assets/diagrams/<hash>.svg`. The `mermaid` shortcode inlines that SVG (keeping the source text for Lite mode). The existing Python `validate` CI job gains a guard that fails if any diagram's SVG is missing or stale — so the GitHub Actions deploy installs no Node/Chromium.

**Tech Stack:** Hugo 0.145 (extended), Python 3 stdlib, `@mermaid-js/mermaid-cli` (`mmdc`, dev-only), existing Telemetry CSS token system.

## Global Constraints

- **Hugo target: 0.145.0** — CI builds with it (`~/bin/hugo` locally). Templates must work on 0.145; do not use APIs newer than 0.145.
- **CI stays pure Python + Hugo** — no Node/Chromium/containers added to `.github/workflows/hugo.yml`. `mmdc` is a dev-only dependency, never installed in CI.
- **No new CSS tokens** — reuse `--node-fill`, `--node-stroke`, `--edge`, `--nlab`, `--surface`, `--border` (defined for `:root`/`html.light`/`html.calm` in `telemetry.css`).
- **Hash contract:** diagram key = `sha256(TrimSpace(source))` hex, first **12** chars, UTF-8. Hugo side: `substr (sha256 (.Inner | strings.TrimSpace)) 0 12`. Python side: `hashlib.sha256(source.strip().encode("utf-8")).hexdigest()[:12]`.
- **Fallback contract:** default + no-JS render the SVG; only `html.pref-lite` shows the `.mermaid` text source (and hides the SVG). Keep `{{ .Inner }}` source in the shortcode markup.
- **No AI commit attribution** — no `Co-Authored-By`, no tool footer (repo convention).
- **Sentinel palette (render → tokenize map):**
  | role | sentinel hex | → CSS var |
  |---|---|---|
  | node fill | `#f01a01` | `var(--node-fill)` |
  | node stroke/border | `#f02a02` | `var(--node-stroke)` |
  | label / node text | `#f03a03` | `var(--nlab)` |
  | edge / line / arrow | `#f04a04` | `var(--edge)` |
  | cluster/subgraph bg | `#f05a05` | `var(--surface)` |
  | cluster/subgraph border | `#f06a06` | `var(--border)` |

  Sentinels are deliberately garish and unique so no real palette color collides.

---

## Task 1: Shared diagram library — extraction, hashing, tokenizing

Pure-Python, mmdc-free, fully unit-testable. Everything the render script and the CI guard share lives here.

**Files:**
- Create: `scripts/mermaid_lib.py`
- Test: `scripts/test_mermaid_lib.py`

**Interfaces:**
- Produces (imported by Tasks 2 & 5):
  - `PALETTE: dict[str, str]` — sentinel-hex → css-var string, per the Global Constraints table.
  - `iter_mermaid_blocks(paths: list[str]) -> Iterator[tuple[str, str]]` — yields `(md_path, source)` for every `{{< mermaid >}}…{{< /mermaid >}}` block; `source` is the raw inner, **not** stripped.
  - `diagram_hash(source: str) -> str` — `sha256(source.strip())` hex, first 12 chars.
  - `tokenize_svg(svg: str) -> str` — replaces sentinel hexes with their css-var (in `<style>` blocks, inline `style=`, and by converting `fill="#…"`/`stroke="#…"` presentation attrs to `style="fill:var(--…)"`).
  - `normalize_svg(svg: str) -> str` — strips fixed `width=`/`height=` on the root `<svg>` (keeps `viewBox` so it scales in `.diag-card`) and adds `role="img"` if absent. Any Mermaid-emitted `<title>`/`<desc>` (from `accTitle`/`accDescr` in the source) passes through untouched.
  - `untokenized_colors(svg: str) -> list[str]` — returns any `#rrggbb`/`#rgb` hex literals still present after tokenizing (the leftover-color guard). Empty list = clean.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_mermaid_lib.py
import mermaid_lib as m

def test_diagram_hash_matches_pinned_contract():
    # sha256("flowchart TD\n  A-->B") first 12 hex chars, computed with
    # hashlib independently and pasted here so the test pins the contract.
    src = "\n  flowchart TD\n    A-->B\n  "
    assert m.diagram_hash(src) == m.diagram_hash(src.strip())  # strip-invariant
    assert len(m.diagram_hash(src)) == 12
    assert m.diagram_hash("a") == "ca978112ca1b"  # sha256("a")[:12]

def test_iter_blocks_extracts_multiple(tmp_path):
    md = tmp_path / "x.md"
    md.write_text('intro\n{{< mermaid >}}\nA-->B\n{{< /mermaid >}}\n'
                  'mid\n{{< mermaid >}}\nC-->D\n{{< /mermaid >}}\n', encoding="utf-8")
    got = [s.strip() for _, s in m.iter_mermaid_blocks([str(md)])]
    assert got == ["A-->B", "C-->D"]

def test_tokenize_replaces_style_block_inline_and_presentation_attr():
    svg = ('<svg><style>.node rect{fill:#f01a01;stroke:#f02a02}</style>'
           '<rect style="fill:#f05a05"/>'
           '<path fill="#f04a04" d="M0 0"/>'
           '<text fill="#f03a03">x</text></svg>')
    out = m.tokenize_svg(svg)
    assert "fill:var(--node-fill)" in out
    assert "stroke:var(--node-stroke)" in out
    assert "fill:var(--surface)" in out
    assert 'style="fill:var(--edge)"' in out       # presentation attr converted
    assert 'fill="#f04a04"' not in out             # old attr gone
    assert "var(--nlab)" in out
    assert m.untokenized_colors(out) == []

def test_untokenized_colors_flags_leftovers():
    assert m.untokenized_colors('<rect style="fill:#abc123"/>') == ["#abc123"]
    assert m.untokenized_colors('<rect style="fill:var(--edge)"/>') == []

def test_normalize_strips_size_adds_role_keeps_viewbox_and_title():
    svg = '<svg width="820" height="410" viewBox="0 0 820 410"><title>x</title></svg>'
    out = m.normalize_svg(svg)
    assert 'width="820"' not in out and 'height="410"' not in out
    assert 'viewBox="0 0 820 410"' in out
    assert 'role="img"' in out
    assert "<title>x</title>" in out   # a11y title passes through
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 -m pytest scripts/test_mermaid_lib.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mermaid_lib'` (or import error). If pytest is unavailable, use `python3 scripts/test_mermaid_lib.py` after adding an `unittest` shim; prefer pytest.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/mermaid_lib.py
"""Shared helpers for pre-rendered Mermaid diagrams.

Extraction, the hash contract, and SVG color-tokenizing live here so the
render script (render-diagrams.py) and the CI guard (verify_visuals.py) can
never drift on the Python side. Standard library only.
"""
import hashlib
import re

# sentinel hex (as fed to mmdc) -> CSS variable (resolved from the cascade)
PALETTE = {
    "#f01a01": "var(--node-fill)",
    "#f02a02": "var(--node-stroke)",
    "#f03a03": "var(--nlab)",
    "#f04a04": "var(--edge)",
    "#f05a05": "var(--surface)",
    "#f06a06": "var(--border)",
}

_BLOCK = re.compile(r"{{<\s*mermaid\s*>}}(.*?){{<\s*/\s*mermaid\s*>}}", re.S)
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")


def iter_mermaid_blocks(paths):
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        for mo in _BLOCK.finditer(txt):
            yield p, mo.group(1)


def diagram_hash(source):
    return hashlib.sha256(source.strip().encode("utf-8")).hexdigest()[:12]


def tokenize_svg(svg):
    out = svg
    # 1) presentation attributes fill="#.."/stroke="#.." -> style="fill:var(..)"
    def _attr(m):
        prop, hexv = m.group(1), m.group(2).lower()
        var = PALETTE.get(hexv)
        return f'style="{prop}:{var}"' if var else m.group(0)
    out = re.sub(r'(fill|stroke)="(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})"', _attr, out)
    # 2) every remaining sentinel occurrence (style blocks + inline style=)
    for hexv, var in PALETTE.items():
        out = re.sub(re.escape(hexv), var, out, flags=re.I)
    return out


def untokenized_colors(svg):
    # colors that survived tokenizing (excluding those already inside var())
    return [h for h in _HEX.findall(svg)]


def normalize_svg(svg):
    # operate only on the opening <svg ...> tag
    m = re.search(r"<svg\b[^>]*>", svg)
    if not m:
        return svg
    tag = m.group(0)
    new = re.sub(r'\s(width|height)="[^"]*"', "", tag)   # drop fixed pixel size
    if "role=" not in new:
        new = new[:4] + ' role="img"' + new[4:]           # after "<svg"
    return svg[:m.start()] + new + svg[m.end():]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 -m pytest scripts/test_mermaid_lib.py -v`
Expected: PASS (5 tests). If `test_diagram_hash_matches_pinned_contract` fails on the `"a"` vector, recompute with `python3 -c "import hashlib;print(hashlib.sha256(b'a').hexdigest()[:12])"` and correct the literal — do not change the implementation.

- [ ] **Step 5: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add scripts/mermaid_lib.py scripts/test_mermaid_lib.py
git commit -m "feat(diagrams): shared mermaid extraction/hash/tokenize lib"
```

---

## Task 2: Render script + mermaid-cli config

Orchestrates `mmdc` over every diagram and writes tokenized SVGs. Integration-tested against one real content file.

**Files:**
- Create: `scripts/render-diagrams.py`
- Create: `scripts/mermaid-config.json` (mmdc `-c` config: base theme + sentinel `themeVariables`)
- Create: `scripts/puppeteer-config.json` (`{ "args": ["--no-sandbox"] }`)
- Create: `package.json` (pins `@mermaid-js/mermaid-cli`; dev-only)
- Create dir: `themes/scryops/assets/diagrams/` (output; committed)

**Interfaces:**
- Consumes: `mermaid_lib.iter_mermaid_blocks`, `diagram_hash`, `tokenize_svg`, `untokenized_colors`.
- Produces: `themes/scryops/assets/diagrams/<hash>.svg` files. CLI: `python3 scripts/render-diagrams.py [content/x.md ...]` (no args = all of `content/**/*.md`); exit non-zero on any render or leftover-color failure.

- [ ] **Step 1: Create the mmdc config with the sentinel palette**

`scripts/mermaid-config.json` — set colors explicitly so Mermaid computes as few derivative shades as possible:

```json
{
  "theme": "base",
  "htmlLabels": false,
  "flowchart": { "htmlLabels": false, "useMaxWidth": true },
  "themeVariables": {
    "background": "transparent",
    "primaryColor": "#f01a01",
    "mainBkg": "#f01a01",
    "secondaryColor": "#f05a05",
    "tertiaryColor": "#f05a05",
    "primaryBorderColor": "#f02a02",
    "nodeBorder": "#f02a02",
    "clusterBkg": "#f05a05",
    "clusterBorder": "#f06a06",
    "primaryTextColor": "#f03a03",
    "textColor": "#f03a03",
    "nodeTextColor": "#f03a03",
    "titleColor": "#f03a03",
    "lineColor": "#f04a04",
    "edgeLabelBackground": "#f05a05",
    "arrowheadColor": "#f04a04",
    "fontFamily": "'IBM Plex Mono', monospace",
    "fontSize": "14px"
  }
}
```

`scripts/puppeteer-config.json`:

```json
{ "args": ["--no-sandbox", "--disable-gpu"] }
```

- [ ] **Step 2: Create package.json pinning mermaid-cli**

```json
{
  "name": "scryops-site-build",
  "private": true,
  "description": "Dev-only diagram tooling. Not shipped, not installed in CI.",
  "devDependencies": {
    "@mermaid-js/mermaid-cli": "10.9.1"
  }
}
```

Then install locally:

Run: `cd /Users/jonhdoe/Repository/scryops-site && npm install`
Expected: creates `node_modules/` and `package-lock.json`; `npx mmdc --version` prints a 10.9.x version.

Add `node_modules/` to `.gitignore` if not already present:

Run: `grep -qx 'node_modules/' .gitignore || printf 'node_modules/\n' >> .gitignore`

- [ ] **Step 3: Write the failing integration test**

```python
# scripts/test_render_diagrams.py
import os, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_render_one_file_produces_tokenized_svgs():
    import mermaid_lib as m
    md = "content/guides/opentelemetry-overview.md"          # 1 diagram
    src = next(s for _, s in m.iter_mermaid_blocks([os.path.join(REPO, md)]))
    h = m.diagram_hash(src)
    out = os.path.join(REPO, "themes/scryops/assets/diagrams", f"{h}.svg")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([sys.executable, "scripts/render-diagrams.py", md],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(out), "expected SVG not written"
    svg = open(out, encoding="utf-8").read()
    assert "<svg" in svg and "var(--node-fill)" in svg
    assert 'role="img"' in svg                      # normalize_svg applied
    assert m.untokenized_colors(svg) == [], f"baked colors leaked: {m.untokenized_colors(svg)}"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 -m pytest scripts/test_render_diagrams.py -v`
Expected: FAIL — `render-diagrams.py` does not exist yet.

- [ ] **Step 5: Write the render script**

```python
#!/usr/bin/env python3
"""Pre-render every {{< mermaid >}} diagram to a theme-tokenized static SVG.

    python3 scripts/render-diagrams.py [content/x.md ...]   # default: all content

Shells to mmdc (dev-only @mermaid-js/mermaid-cli) with a sentinel palette, then
rewrites the baked colors to CSS vars via mermaid_lib. Writes
themes/scryops/assets/diagrams/<hash>.svg. Exits non-zero if any diagram fails
to render or if a baked color survives tokenizing (leftover-color guard).
Standard library + local mmdc only.
"""
import glob
import os
import subprocess
import sys
import tempfile

import mermaid_lib as m

OUT_DIR = os.path.join("themes", "scryops", "assets", "diagrams")
CONFIG = os.path.join("scripts", "mermaid-config.json")
PUPPETEER = os.path.join("scripts", "puppeteer-config.json")
GREEN, RED, OFF = "\033[32m", "\033[31m", "\033[0m"


def render_one(source):
    """Return tokenized SVG text for one diagram source, or raise."""
    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, "d.mmd")
        svg_path = os.path.join(td, "d.svg")
        with open(src_path, "w", encoding="utf-8") as fh:
            fh.write(source.strip() + "\n")
        cmd = ["npx", "-y", "mmdc", "-i", src_path, "-o", svg_path,
               "-c", CONFIG, "-p", PUPPETEER, "-b", "transparent"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(svg_path):
            raise RuntimeError(r.stdout + r.stderr)
        raw = open(svg_path, encoding="utf-8").read()
    svg = m.normalize_svg(m.tokenize_svg(raw))
    leftover = m.untokenized_colors(svg)
    if leftover:
        raise RuntimeError(
            "baked colors survived tokenizing: " + ", ".join(sorted(set(leftover)))
            + "\n  -> add each to PALETTE (mermaid_lib.py) + mermaid-config.json themeVariables")
    return svg


def main():
    if not os.path.isdir(os.path.join("themes", "scryops")):
        print(f"{RED}run me from the repo root{OFF}")
        return 2
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sys.argv[1:] or glob.glob("content/**/*.md", recursive=True)
    n, failed = 0, 0
    for md, source in m.iter_mermaid_blocks(files):
        h = m.diagram_hash(source)
        dst = os.path.join(OUT_DIR, f"{h}.svg")
        try:
            svg = render_one(source)
        except RuntimeError as e:
            print(f"{RED}FAIL{OFF} {md} [{h}]: {e}")
            failed += 1
            continue
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"{GREEN}OK{OFF}   {md} -> {dst}")
        n += 1
    print(f"\nrendered {n} diagram(s), {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 -m pytest scripts/test_render_diagrams.py -v`
Expected: PASS. If it fails with leftover colors, the error names each hex — add it to `PALETTE` (Task 1) and to `mermaid-config.json` `themeVariables` (mapping it to the right sentinel), then re-run. This is the expected tuning loop.

- [ ] **Step 7: Render all diagrams**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 scripts/render-diagrams.py`
Expected: `rendered 52 diagram(s), 0 failed` (count approximate). If any fail, resolve leftover colors as above before continuing.

- [ ] **Step 8: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add package.json package-lock.json .gitignore \
  scripts/render-diagrams.py scripts/test_render_diagrams.py \
  scripts/mermaid-config.json scripts/puppeteer-config.json \
  themes/scryops/assets/diagrams/
git commit -m "feat(diagrams): render mermaid to theme-tokenized static SVG"
```

---

## Task 3: Shortcode inlines the SVG (source kept for Lite)

**Files:**
- Modify: `themes/scryops/layouts/shortcodes/mermaid.html`

**Interfaces:**
- Consumes: committed `assets/diagrams/<hash>.svg` (Task 2); hash contract (Global Constraints).
- Produces: rendered `<figure class="diagram">` with inline `<svg>` and a dormant `.mermaid` source div.

- [ ] **Step 1: Rewrite the shortcode**

```go-html-template
{{- $src := .Inner | strings.TrimSpace -}}
{{- $hash := substr (sha256 $src) 0 12 -}}
{{- $svg := resources.Get (printf "diagrams/%s.svg" $hash) -}}
{{- if not $svg -}}
  {{- errorf "mermaid: no pre-rendered SVG for hash %s (in %s) — run scripts/render-diagrams.py" $hash .Page.File.Path -}}
{{- end -}}
<figure class="diagram">
  <div class="diag-card">{{ $svg.Content | safeHTML }}</div>
  <div class="mermaid">{{ .Inner }}</div>
</figure>
```

- [ ] **Step 2: Build with Hugo 0.145 to verify resolution**

Run: `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo --gc --minify --destination /tmp/scryops-check 2>&1 | tail -20`
Expected: build succeeds, `0 errors`. A hash mismatch would surface as `ERROR mermaid: no pre-rendered SVG for hash …` — if so, the Hugo↔Python hash contract diverged; verify both trim identically and use `sha256` first-12.

- [ ] **Step 3: Confirm the SVG is inlined, not the CDN div**

Run: `grep -c '<svg' /tmp/scryops-check/guides/opentelemetry-overview/index.html`
Expected: `>= 1`.
Run: `grep -c 'cdn.jsdelivr.net/npm/mermaid' /tmp/scryops-check/guides/opentelemetry-overview/index.html`
Expected: `1` (still present — removed in Task 6; this confirms ordering).

- [ ] **Step 4: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/layouts/shortcodes/mermaid.html
git commit -m "feat(diagrams): inline pre-rendered SVG in mermaid shortcode"
```

---

## Task 4: Repoint the CSS fallback (no-JS shows SVG; Lite shows source)

**Files:**
- Modify: `themes/scryops/assets/css/telemetry.css:182-187`

**Interfaces:**
- Consumes: `.diagram .mermaid` (source div) and `.diag-card > svg` (Task 3 output).

- [ ] **Step 1: Replace the fallback rules**

Replace the current block (the comment + the two `html.pref-lite … , html:not(.js) …` rules) with:

```css
/* Mermaid fallback — diagrams are static inline SVG (no JS needed), so no-JS
   visitors get the real diagram. The .mermaid source stays dormant and is
   shown as a readable text block only in Lite/data-saver mode. */
.diagram .mermaid{display:none}
html.pref-lite .diagram .diag-card > svg{display:none}
html.pref-lite .diagram .mermaid{display:block;white-space:pre-wrap;font-family:var(--font-code);font-size:12px;line-height:1.5;color:var(--code-muted);background:var(--code-bg);border:1px solid var(--code-bd);border-radius:var(--radius);padding:14px 16px;overflow-x:auto}
html.pref-lite .diagram .mermaid::before{content:"diagram source";display:block;color:var(--eco);font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
```

- [ ] **Step 2: Verify the CSS compiles into the build**

Run: `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo --gc --minify --destination /tmp/scryops-check 2>&1 | tail -5`
Expected: `0 errors`.
Run: `grep -o 'diagram .mermaid{display:none}' /tmp/scryops-check/css/style.css | head -1`
Expected: matches (rule present in the shipped CSS). Visual dark/light/calm + Lite check happens in Task 7.

- [ ] **Step 3: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/assets/css/telemetry.css
git commit -m "feat(diagrams): no-JS shows SVG, Lite shows diagram source"
```

---

## Task 5: CI guard — every diagram has a committed, current SVG

**Files:**
- Modify: `scripts/verify_visuals.py`

**Interfaces:**
- Consumes: `mermaid_lib.iter_mermaid_blocks`, `diagram_hash`.
- Produces: hard-fail in the existing `validate` job if a diagram's SVG is missing, plus a warning for orphan SVGs.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_verify_guard.py
import os, subprocess, sys, glob
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_guard_passes_clean():
    r = subprocess.run([sys.executable, "scripts/verify_visuals.py"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "diagram SVG" in (r.stdout + r.stderr)  # the new section ran

def test_guard_fails_on_missing_svg(tmp_path):
    import mermaid_lib as m
    # pick any rendered svg, move it aside, expect non-zero, restore
    svgs = glob.glob(os.path.join(REPO, "themes/scryops/assets/diagrams/*.svg"))
    victim = svgs[0]; bak = victim + ".bak"
    os.rename(victim, bak)
    try:
        r = subprocess.run([sys.executable, "scripts/verify_visuals.py"],
                           cwd=REPO, capture_output=True, text=True)
        assert r.returncode != 0
        assert "render-diagrams" in (r.stdout + r.stderr)
    finally:
        os.rename(bak, victim)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 -m pytest scripts/test_verify_guard.py -v`
Expected: FAIL — the "diagram SVG" section doesn't exist yet.

- [ ] **Step 3: Add the guard to `verify_visuals.py`**

At the top of the file, add the import (after the existing `import sys, os, re, glob, subprocess`):

```python
import mermaid_lib
```

Add this function above `def main():`:

```python
def check_diagram_svgs(articles):
    """Every {{< mermaid >}} block must have a committed, current SVG; warn on orphans."""
    out_dir = os.path.join("themes", "scryops", "assets", "diagrams")
    referenced = set()
    hard = False
    print(f"\n{DIM}— diagram SVG pre-render —{OFF}")
    for md, source in mermaid_lib.iter_mermaid_blocks(articles):
        h = mermaid_lib.diagram_hash(source)
        referenced.add(h)
        if os.path.exists(os.path.join(out_dir, f"{h}.svg")):
            ok(f"{md} [{h}]: SVG present")
        else:
            fail(f"{md} [{h}]: missing SVG — run scripts/render-diagrams.py")
            hard = True
    # orphan check only meaningful on a full scan (no file args)
    if len(sys.argv) <= 1 and os.path.isdir(out_dir):
        for svg in glob.glob(os.path.join(out_dir, "*.svg")):
            h = os.path.splitext(os.path.basename(svg))[0]
            if h not in referenced:
                warn(f"orphan SVG {svg} — no diagram references it (safe to git rm)")
    return hard
```

In `main()`, immediately before the `print()`/`if hard_fail:` finale, call it:

```python
    if check_diagram_svgs(articles):
        hard_fail = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 -m pytest scripts/test_verify_guard.py -v`
Expected: PASS (2 tests).
Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 scripts/verify_visuals.py; echo "exit=$?"`
Expected: `exit=0`, with an "— diagram SVG pre-render —" section listing OK lines.

- [ ] **Step 5: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add scripts/verify_visuals.py scripts/test_verify_guard.py
git commit -m "feat(ci): guard that every mermaid diagram has a committed SVG"
```

---

## Task 6: Remove the runtime, delete dead vendor JS, update colophon

Do this only after Tasks 1–5 are green — the SVGs must already ship.

**Files:**
- Modify: `themes/scryops/layouts/_default/baseof.html:160-182` (delete the Mermaid loader block)
- Delete: `themes/scryops/assets/js/mermaid-init.js`
- Delete: `themes/scryops/assets/js/vendor/mermaid.min.js`
- Modify: `content/colophon/_index.md:19`

- [ ] **Step 1: Delete the Mermaid loader block in baseof.html**

Remove the entire block from the `{{/* Mermaid — load the runtime only when… */}}` comment (line ~160) through the closing `</script>` at line ~182 (the `(function(){ … cdn.jsdelivr.net/npm/mermaid@10.9.6 … })()` IIFE and its `$mermaidInit := resources.Get "js/mermaid-init.js"` line). Leave the following `{{/* reading preferences … */}}` block intact.

- [ ] **Step 2: Delete the JS files**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git rm themes/scryops/assets/js/mermaid-init.js themes/scryops/assets/js/vendor/mermaid.min.js
```

- [ ] **Step 3: Update the colophon diagrams row**

In `content/colophon/_index.md:19`, replace:

```html
  <div class="co-row"><span class="co-k">diagrams</span><span class="co-v">Mermaid via CDN <span class="eco">(self-host pending)</span></span></div>
```

with:

```html
  <div class="co-row"><span class="co-k">diagrams</span><span class="co-v">Mermaid · pre-rendered static SVG <span class="eco">(0 JS, themes via CSS vars)</span></span></div>
```

- [ ] **Step 4: Build and confirm the runtime is gone**

Run: `cd /Users/jonhdoe/Repository/scryops-site && ~/bin/hugo --gc --minify --destination /tmp/scryops-check 2>&1 | tail -5`
Expected: `0 errors`. A dangling `resources.Get "js/mermaid-init.js"` would error here — good signal you missed part of the block.
Run: `grep -rc 'cdn.jsdelivr.net/npm/mermaid\|mermaid-init\|mermaid.min.js' /tmp/scryops-check/ | grep -v ':0' | head`
Expected: no output (zero matches across the built site).

- [ ] **Step 5: Commit**

```bash
cd /Users/jonhdoe/Repository/scryops-site
git add themes/scryops/layouts/_default/baseof.html content/colophon/_index.md
git commit -m "feat(diagrams): drop CDN mermaid runtime + delete 3.2MB vendor JS"
```

---

## Task 7: Full verification (dark / light / calm / no-JS / Lite / footprint)

No code — this is the acceptance gate. Uses the preview tooling.

**Files:** none (verification only).

- [ ] **Step 1: Ensure the preview launch config exists**

Confirm `.claude/launch.json` has a Hugo 0.145 dev-server entry (runtimeExecutable pointing at `~/bin/hugo`, args `["server","--port","1313"]`). If missing, create it. Start the server via the preview tool (not raw Bash).

- [ ] **Step 2: Load a diagram-heavy page**

Navigate the preview to `/guides/slos-and-error-budgets/` (7 diagrams). Take a snapshot; confirm `<svg` diagrams render inside `.diag-card` (no raw Mermaid text, no console request to `cdn.jsdelivr.net`).

- [ ] **Step 3: Verify all three themes invert**

For each of dark (default), `html.light`, `html.calm` (toggle via the reading-prefs UI or by setting the class): inspect a diagram node's computed `fill` and confirm it equals the theme's `--node-fill` value (`#10191A` dark / `#EAF1ED` light / `#221D14` calm) and edges match `--edge`. Cache-bust `style.css` (append `?v=N`) so CSS edits are not served stale.

- [ ] **Step 4: Verify no-JS renders the SVG**

Disable JavaScript (preview eval to block, or a no-JS context) and reload. Expected: the SVG diagrams still render (they need no JS); the page does NOT fall back to the text "diagram source" block.

- [ ] **Step 5: Verify Lite mode shows the text source**

Enable Lite mode (`html.pref-lite`, via the reading-prefs toggle). Expected: SVGs hidden, each diagram shows the styled "DIAGRAM SOURCE" text block.

- [ ] **Step 6: Confirm the footprint drop**

Compare the page transfer size / footprint badge for `/guides/slos-and-error-budgets/` before (main: ~1 MB with the CDN runtime) and after (this branch: KB). Record the numbers. Expected: KB range, runtime eliminated.

- [ ] **Step 7: Full validate + build dry run (CI parity)**

Run: `cd /Users/jonhdoe/Repository/scryops-site && python3 scripts/verify_visuals.py && ~/bin/hugo --gc --minify --destination /tmp/scryops-final 2>&1 | tail -5`
Expected: validator `exit 0` with the diagram-SVG section all-OK; Hugo `0 errors`.

- [ ] **Step 8: Finish the branch**

Use the `superpowers:finishing-a-development-branch` skill to choose merge/PR. (PR body: no AI footer, per repo convention.)

---

## Notes for the implementer

- **Run order matters:** Task 2 must render the SVGs *before* Task 3's shortcode build (it `errorf`s without them) and before Task 5's guard. Do not reorder.
- **The leftover-color guard is your friend.** If a theme looks wrong after Task 7, first re-run `python3 scripts/render-diagrams.py` and check for any `untokenized_colors` output — a baked color that escaped is the usual cause. Add it to `PALETTE` + `mermaid-config.json` and re-render.
- **Hugo version:** always verify with `~/bin/hugo` (0.145), never the 0.159 on `PATH` — a template that works on 0.159 may not on the CI version.
