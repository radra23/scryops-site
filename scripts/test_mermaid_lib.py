import xml.dom.minidom

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

def test_tokenize_merges_fill_and_stroke_on_same_element():
    # Realistic Mermaid marker/arrowhead polygon: both fill and stroke
    # presentation attrs on one element. Each was independently rewritten
    # to its own style="..." attr, producing two style attrs on one tag
    # (invalid XML -> "duplicate attribute" on parse).
    svg = '<svg><polygon fill="#f01a01" stroke="#f02a02"/></svg>'
    out = m.tokenize_svg(svg)
    assert out.count('style=') == 1
    assert "fill:var(--node-fill)" in out
    assert "stroke:var(--node-stroke)" in out
    xml.dom.minidom.parseString(out)  # raises "duplicate attribute" if unfixed

def test_tokenize_merges_preexisting_style_with_presentation_attr():
    # Element already has a style="..." AND a fill/stroke presentation attr;
    # conversion must not add a second style attribute.
    svg = '<svg><rect style="opacity:0.5" fill="#f01a01"/></svg>'
    out = m.tokenize_svg(svg)
    assert out.count('style=') == 1
    assert "opacity:0.5" in out
    assert "fill:var(--node-fill)" in out
    xml.dom.minidom.parseString(out)

def test_untokenized_colors_flags_leftovers():
    assert m.untokenized_colors('<rect style="fill:#abc123"/>') == ["#abc123"]
    assert m.untokenized_colors('<rect style="fill:var(--edge)"/>') == []

def test_short_sentinel_does_not_corrupt_longer_hex():
    # #000 is a 3-char sentinel in PALETTE; it must not match as a prefix
    # inside an unrelated 6-char hex color like #000fff.
    out = m.tokenize_svg('<rect fill="#000fff"/>')
    assert '#000fff' in out
    assert 'var(--nlab)fff' not in out
    # a standalone #000 (not part of a longer hex) must still tokenize.
    solo = m.tokenize_svg('<rect style="fill:#000"/>')
    assert 'var(--nlab)' in solo  # PALETTE["#000"] == "var(--nlab)"

def test_tokenize_and_guard_handle_rgba_sentinel():
    # PALETTE["#f05a05"] -> var(--surface); its rgb channels are (240, 90, 5).
    r, g, b = m._hex_to_rgb('#f05a05')
    svg = f'<rect style="fill:rgba({r}, {g}, {b}, 0.5)"/>'
    out = m.tokenize_svg(svg)
    assert 'var(--surface)' in out
    assert f'rgba({r}, {g}, {b}, 0.5)' not in out
    # tokenized output has no leftover sentinel colors
    assert m.untokenized_colors(out) == []
    # a sentinel rgba that was NOT run through tokenize_svg is correctly
    # flagged by the guard as an un-tokenized sentinel leftover.
    untouched = f'<rect style="fill:rgba({r}, {g}, {b}, 0.5)"/>'
    assert f'rgba({r}, {g}, {b}, 0.5)' in m.untokenized_colors(untouched)

def test_normalize_upgrades_existing_role_to_img():
    svg = '<svg role="graphics-document document" viewBox="0 0 10 10"></svg>'
    out = m.normalize_svg(svg)
    assert 'role="img"' in out
    assert 'graphics-document' not in out

def test_normalize_strips_size_adds_role_keeps_viewbox_and_title():
    svg = '<svg width="820" height="410" viewBox="0 0 820 410"><title>x</title></svg>'
    out = m.normalize_svg(svg)
    assert 'width="820"' not in out and 'height="410"' not in out
    assert 'viewBox="0 0 820 410"' in out
    assert 'role="img"' in out
    assert "<title>x</title>" in out   # a11y title passes through
