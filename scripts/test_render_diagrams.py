import os, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_render_one_file_produces_tokenized_svgs(tmp_path):
    import mermaid_lib as m
    md = "content/guides/opentelemetry-overview.md"          # 1 diagram
    src = next(s for _, s in m.iter_mermaid_blocks([os.path.join(REPO, md)]))
    h = m.diagram_hash(src)
    committed = os.path.join(REPO, "themes/scryops/assets/diagrams", f"{h}.svg")
    before = open(committed, "rb").read() if os.path.exists(committed) else None
    # render into tmp_path, never over the committed SVG: a failed or
    # timed-out mmdc run must not leave the repo with a missing diagram
    env = dict(os.environ, SCRYOPS_DIAGRAM_OUT_DIR=str(tmp_path))
    r = subprocess.run([sys.executable, "scripts/render-diagrams.py", md],
                       cwd=REPO, env=env, capture_output=True, text=True)
    after = open(committed, "rb").read() if os.path.exists(committed) else None
    assert after == before, "render test touched the committed SVG"
    assert r.returncode == 0, r.stdout + r.stderr
    out = tmp_path / f"{h}.svg"
    assert out.exists(), "expected SVG not written"
    svg = out.read_text(encoding="utf-8")
    assert "<svg" in svg and "var(--node-fill)" in svg
    assert 'role="img"' in svg                      # normalize_svg applied
    assert m.untokenized_colors(svg) == [], f"baked colors leaked: {m.untokenized_colors(svg)}"
