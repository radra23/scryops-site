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
