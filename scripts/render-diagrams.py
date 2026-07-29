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
