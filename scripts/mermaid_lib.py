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


_STYLE_ATTR = re.compile(r'style="([^"]*)"')
_START_TAG = re.compile(r"<[a-zA-Z][\w:-]*\b[^>]*>")


def _merge_duplicate_style_attrs(tag):
    styles = _STYLE_ATTR.findall(tag)
    if len(styles) < 2:
        return tag
    # dedupe leading/trailing semicolons from each fragment, then join with ";"
    parts = [s.strip().strip(";").strip() for s in styles if s.strip().strip(";").strip()]
    merged = ";".join(parts)
    # drop every style="..." occurrence, then insert one merged style attr
    # right after the tag name (order among other attrs doesn't matter for SVG).
    stripped = _STYLE_ATTR.sub("", tag)
    stripped = re.sub(r"\s{2,}", " ", stripped)  # collapse gaps left behind
    name_end = re.match(r"<[a-zA-Z][\w:-]*", stripped).end()
    return stripped[:name_end] + f' style="{merged}"' + stripped[name_end:]


def _merge_duplicate_style_attrs_in_svg(svg):
    return _START_TAG.sub(lambda m: _merge_duplicate_style_attrs(m.group(0)), svg)


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
    # 3) an element may now carry 2+ style="..." attrs (step 1 converting both
    #    fill and stroke independently, or a pre-existing style= plus a
    #    converted presentation attr) -> collapse to a single merged style=.
    out = _merge_duplicate_style_attrs_in_svg(out)
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
