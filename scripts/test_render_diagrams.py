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
