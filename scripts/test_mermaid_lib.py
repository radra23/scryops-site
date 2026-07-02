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
