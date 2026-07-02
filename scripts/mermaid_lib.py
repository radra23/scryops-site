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
    # Mermaid's flowchart stylesheet hardcodes `.node .katex path { fill:
    # #000; stroke: #000; }` with no themeVariable hook (see
    # node_modules/mermaid/dist/styles-*.js) -- unused dead CSS whenever a
    # diagram has no KaTeX math, but it still leaks into every render. Not a
    # sentinel fed to mmdc; tokenized as a literal leftover instead.
    "#000": "var(--nlab)",
    # sequenceDiagram: actor-box fill and lifeline stroke are hardcoded JS
    # literals in mermaid's renderer (rect2.fill = "#eaeaea", stroke =
    # "#999"/"#666" on the actor line), applied whenever an actor has no
    # explicit `actor.properties.class` override. No themeVariable reaches
    # them, so they leak into every sequence diagram the same way.
    "#eaeaea": "var(--node-fill)",
    "#999": "var(--node-stroke)",
    "#666": "var(--node-stroke)",
    # sequenceDiagram: a second hardcoded background rect (`fill:
    # "#EDF2AE"`) drawn behind actor boxes with links/menus.
    "#EDF2AE": "var(--surface)",
    # stateDiagram-v2: dead CSS for composite/nested-state and note
    # rendering (`.stateGroup .alt-composit`, note bkg/text) -- hardcoded
    # literals in mermaid's stylesheet template, unused whenever a diagram
    # has no composite state / note, but always emitted.
    "#e0e0e0": "var(--surface)",
    "#fff5ad": "var(--surface)",
    "#333": "var(--nlab)",

    # --- Author-authored semantic colors -------------------------------
    # ~24 content diagrams hand-author `style X fill:F,stroke:S,color:C` /
    # `classDef ... fill:F,stroke:S,color:C` triads to highlight
    # success/error/warning/info states (green/red/orange/blue), using
    # hex literals the author chose directly in the markdown source --
    # these are genuine diagram content, not Mermaid-derived shades, so no
    # themeVariable or mmdc sentinel can intercept them. Tokenized here by
    # exact hex so the semantic intent survives, reusing the site's
    # existing semantic tokens (no new tokens, per the design spec).
    # fill role -> all dark/near-black backgrounds regardless of hue family
    "#161616": "var(--surface)",
    "#1A1A2E": "var(--surface)",
    "#1C1C1C": "var(--surface)",
    "#1C2A1C": "var(--surface)",
    "#2A0A0A": "var(--surface)",
    "#2A1414": "var(--surface)",
    "#2A1A0A": "var(--surface)",
    "#2A1A1A": "var(--surface)",
    "#2A2410": "var(--surface)",
    # stroke role, grouped by hue family
    "#3A6FAF": "var(--cyan)",     # blue/info
    "#1C7A2E": "var(--green)",    # success
    "#CC4444": "var(--danger)",   # error
    "#CD384B": "var(--danger)",   # error
    "#D4820A": "var(--warn)",     # warning
    "#2A2A2A": "var(--border)",   # neutral/default classDef stroke
    # color (text) role, grouped by hue family
    "#5B8DEF": "var(--cyan)",
    "#28CA41": "var(--green)",
    "#FF6060": "var(--danger)",
    "#F5A623": "var(--warn)",
    "#A8A8A0": "var(--muted)",    # neutral/default classDef text
    # bare `style X fill:#hex` single-value highlights (no stroke/color)
    "#4ecdc4": "var(--cyan)",
    "#66bb6a": "var(--green)",
    "#99ccff": "var(--cyan)",
    "#cccccc": "var(--muted)",
    "#ff6b6b": "var(--danger)",
    "#ff9999": "var(--danger)",
    "#ffa726": "var(--warn)",
    "#ffcc99": "var(--warn)",
}

_BLOCK = re.compile(r"{{<\s*mermaid\s*>}}(.*?){{<\s*/\s*mermaid\s*>}}", re.S)
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
# mermaid's stylesheet helper (`ne`/rgba-from-hex) renders some
# themeVariables -- e.g. edgeLabelBackground for the (unused, since we set
# htmlLabels:false) `.labelBkg` HTML-label rule -- as `rgba(r, g, b, a)`
# instead of a hex literal. Those never match a `#hex` sentinel, so without
# this they'd tokenize-miss AND guard-miss (silent, not a loud failure).
_RGB_FUNC = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)")


def _hex_to_rgb(hexv):
    h = hexv.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_RGB_TO_VAR = {_hex_to_rgb(h): v for h, v in PALETTE.items() if _HEX.fullmatch(h)}


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
    # 2b) rgb()/rgba() forms of a sentinel (e.g. mermaid's alpha-blended
    #     `.labelBkg` rule) -- match on the (r,g,b) channel tuple, alpha and
    #     all, since var() can't carry a separate opacity here.
    def _rgb(m):
        rgb = tuple(int(x) for x in m.groups())
        var = _RGB_TO_VAR.get(rgb)
        return var if var else m.group(0)
    out = _RGB_FUNC.sub(_rgb, out)
    # 3) an element may now carry 2+ style="..." attrs (step 1 converting both
    #    fill and stroke independently, or a pre-existing style= plus a
    #    converted presentation attr) -> collapse to a single merged style=.
    out = _merge_duplicate_style_attrs_in_svg(out)
    return out


def untokenized_colors(svg):
    # colors that survived tokenizing (excluding those already inside var())
    leftovers = list(_HEX.findall(svg))
    for m in _RGB_FUNC.finditer(svg):
        rgb = tuple(int(x) for x in m.groups())
        if rgb in _RGB_TO_VAR:
            leftovers.append(m.group(0))
    return leftovers


def normalize_svg(svg):
    # operate only on the opening <svg ...> tag
    m = re.search(r"<svg\b[^>]*>", svg)
    if not m:
        return svg
    tag = m.group(0)
    new = re.sub(r'\s(width|height)="[^"]*"', "", tag)   # drop fixed pixel size
    if 'role="' in new:
        # mmdc/mermaid ships its own role (e.g. "graphics-document document")
        # -- a static, pre-rendered SVG is presentational, so normalize to img.
        new = re.sub(r'role="[^"]*"', 'role="img"', new)
    else:
        new = new[:4] + ' role="img"' + new[4:]           # after "<svg"
    return svg[:m.start()] + new + svg[m.end():]
