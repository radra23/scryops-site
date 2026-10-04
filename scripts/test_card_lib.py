"""Tests for the share-card pipeline (card_lib.py + render-cards.py).

card_lib tests use the standard library only (hand-built PNGs, a throwaway
content/ tree), matching CI, where Pillow is not installed. The renderer tests
skip themselves when Pillow / fontTools / PyYAML are missing.

Run: /opt/homebrew/bin/pytest scripts/test_card_lib.py
"""
import importlib.util, os, struct, zlib
import pytest
import card_lib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- helpers ----------

def png_with_text(path, key=None, value=None):
    """Write a 1x1 PNG, optionally carrying one tEXt chunk (stdlib only)."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    parts = [b"\x89PNG\r\n\x1a\n", chunk(b"IHDR", ihdr)]
    if key is not None:
        parts.append(chunk(b"tEXt", key.encode("latin-1") + b"\x00" + value.encode("latin-1")))
    parts += [chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")), chunk(b"IEND", b"")]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"".join(parts))


def write_md(path, fm, body="Body text.\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\n{fm}\n---\n\n{body}")


FM = '''title: "A Title"
date: 2026-10-01
draft: false
excerpt: "An excerpt."
readtime: 5
tags: ["Tracing", "Observability"]'''


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A throwaway repo root with content/ and static/cards/, as the cwd."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------- frontmatter parsing ----------

def test_raw_field_captures_an_indented_block_and_stops_at_the_next_key(site):
    write_md("content/guides/a.md", FM + '''
card:
  panel:
    - {key: error_rate, value: "0.3%", state: ok}
weight: 3''')
    fm = card_lib.frontmatter("content/guides/a.md")
    block = card_lib.raw_field(fm, "card")
    assert block.startswith("card:")
    assert "error_rate" in block
    assert "weight" not in block
    assert card_lib.raw_field(fm, "title") == 'title: "A Title"'
    assert card_lib.raw_field(fm, "missing") == ""


def test_is_published(site):
    assert card_lib.is_published("draft: false")
    assert card_lib.is_published("title: x")                 # no draft key = published
    assert not card_lib.is_published("title: x\ndraft: true")
    assert not card_lib.is_published("draft:   true  ")


def test_pages_lists_published_pages_only(site):
    write_md("content/guides/live.md", FM)
    write_md("content/guides/wip.md", FM.replace("draft: false", "draft: true"))
    write_md("content/guides/_index.md", 'title: "Guides"')
    write_md("content/colophon/_index.md", 'title: "Colophon"')   # not a card section
    write_md("content/qa/q.md", FM)
    got = {(s, st) for s, st, _ in card_lib.pages()}
    assert got == {("guides", "live"), ("qa", "q")}


# ---------- input hash ----------

def test_hash_tracks_card_inputs_but_not_body(site, monkeypatch):
    md = "content/articles/a.md"
    write_md(md, FM)
    base = card_lib.input_hash("articles", "a", md)

    write_md(md, FM, body="A completely different body.\n")
    assert card_lib.input_hash("articles", "a", md) == base, "body text must not affect the card"

    for old, new in [('"A Title"', '"Another Title"'),
                     ('"Tracing"', '"Logs"'),
                     ('"An excerpt."', '"Changed."')]:
        write_md(md, FM.replace(old, new))
        assert card_lib.input_hash("articles", "a", md) != base, f"{old} -> {new} must change the hash"

    write_md(md, FM + "\ncard:\n  panel:\n    - {key: k, value: v, state: ok}")
    assert card_lib.input_hash("articles", "a", md) != base, "a card: block must change the hash"

    write_md(md, FM)
    monkeypatch.setattr(card_lib, "RENDER_VERSION", "999")
    assert card_lib.input_hash("articles", "a", md) != base, "RENDER_VERSION must change the hash"


def test_hash_depends_on_section_and_stem(site):
    write_md("content/guides/a.md", FM)
    h = card_lib.input_hash("guides", "a", "content/guides/a.md")
    assert h != card_lib.input_hash("howtos", "a", "content/guides/a.md")
    assert h != card_lib.input_hash("guides", "b", "content/guides/a.md")


# ---------- PNG tEXt round trip ----------

def test_read_png_hash(site):
    png_with_text("x.png", card_lib.HASH_KEY, "abc123")
    assert card_lib.read_png_hash("x.png") == "abc123"
    png_with_text("other.png", "Software", "something")
    assert card_lib.read_png_hash("other.png") is None
    png_with_text("plain.png")
    assert card_lib.read_png_hash("plain.png") is None
    assert card_lib.read_png_hash("missing.png") is None
    with open("not.png", "wb") as f:
        f.write(b"GIF89a")
    assert card_lib.read_png_hash("not.png") is None


# ---------- stale / orphan detection (what CI enforces) ----------

def test_stale_cards_missing_then_current_then_stale(site):
    md = "content/guides/a.md"
    write_md(md, FM)
    problems = dict(card_lib.stale_cards())
    assert card_lib.card_path("guides", "a") in problems
    assert card_lib.DEFAULT_CARD in problems

    png_with_text(card_lib.card_path("guides", "a"), card_lib.HASH_KEY, card_lib.input_hash("guides", "a", md))
    png_with_text(card_lib.DEFAULT_CARD, card_lib.HASH_KEY, card_lib.default_hash())
    assert card_lib.stale_cards() == []

    write_md(md, FM.replace('"A Title"', '"Retitled"'))
    problems = card_lib.stale_cards()
    assert [p for p, _ in problems] == [card_lib.card_path("guides", "a")]
    assert "stale" in problems[0][1]


def test_orphan_cards(site):
    write_md("content/guides/a.md", FM)
    png_with_text(card_lib.card_path("guides", "a"))
    png_with_text(card_lib.DEFAULT_CARD)
    png_with_text(card_lib.card_path("guides", "gone"))
    write_md("content/guides/wip.md", FM.replace("draft: false", "draft: true"))
    png_with_text(card_lib.card_path("guides", "wip"))         # unpublished -> orphan
    assert sorted(card_lib.orphan_cards()) == sorted([card_lib.card_path("guides", "gone"),
                                                       card_lib.card_path("guides", "wip")])


# ---------- renderer (needs Pillow, fontTools, PyYAML) ----------

@pytest.fixture
def rc(monkeypatch):
    pytest.importorskip("PIL")
    pytest.importorskip("fontTools")
    pytest.importorskip("yaml")
    monkeypatch.chdir(REPO)                                     # fonts + telemetry.css are repo-relative
    spec = importlib.util.spec_from_file_location("render_cards", os.path.join(REPO, "scripts", "render-cards.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_panel_rejects_a_fifth_row(rc, tmp_path):
    rows = "\n".join(f"    - {{key: k{i}, value: v, state: ok}}" for i in range(5))
    md = tmp_path / "a.md"
    write_md(str(md), FM + "\ncard:\n  panel:\n" + rows)
    with pytest.raises(SystemExit, match="4 at most"):
        rc.page_card("articles", "a", str(md))


def test_panel_rejects_an_unknown_state(rc, tmp_path):
    md = tmp_path / "a.md"
    write_md(str(md), FM + "\ncard:\n  panel:\n    - {key: k, value: v, state: fine}")
    with pytest.raises(SystemExit, match="ok\\|warn\\|error"):
        rc.page_card("articles", "a", str(md))


def test_saved_card_is_1200x630_with_exact_frame_and_hash(rc, tmp_path):
    from PIL import Image
    md = tmp_path / "a.md"
    write_md(str(md), FM + '''
card:
  panel:
    - {key: error_rate, value: "0.3%", state: ok}
    - {key: checkout.total, value: "$0.00", state: warn, label: "200 OK, no error"}''')
    out = tmp_path / "cards" / "a.png"
    rc.save(rc.page_card("articles", "a", str(md)), str(out), "deadbeef")

    assert card_lib.read_png_hash(str(out)) == "deadbeef"
    im = Image.open(out)
    assert im.size == (1200, 630)
    assert im.mode == "P"                                       # quantized, small
    rgb = im.convert("RGB")
    frame = rc.tokens()["frame"]
    # every straight-edge frame pixel is the exact token, not a blended neighbour
    for x in (60, 600, 1139):
        for y in (1, 2, 3, 626, 627, 628):
            assert "#%02X%02X%02X" % rgb.getpixel((x, y)) == frame.upper(), (x, y)
    for y in (60, 315, 569):
        for x in (1, 2, 3, 1196, 1197, 1198):
            assert "#%02X%02X%02X" % rgb.getpixel((x, y)) == frame.upper(), (x, y)


def test_card_title_overrides_the_headline_only(rc):
    assert rc.headline({"title": "Long Page Title"}) == "Long Page Title"
    assert rc.headline({"title": "Long Page Title", "card": {"title": "  Short  "}}) == "Short"
    assert rc.headline({"title": "T", "card": {"panel": []}}) == "T"     # card block without a title
    for bad in ("", "   ", 42, ["x"]):
        with pytest.raises(SystemExit, match="card.title"):
            rc.headline({"title": "T", "card": {"title": bad}})


def test_card_title_changes_the_hash(site):
    md = "content/guides/a.md"
    write_md(md, FM)
    base = card_lib.input_hash("guides", "a", md)
    write_md(md, FM + '\ncard:\n  title: "Short"')
    assert card_lib.input_hash("guides", "a", md) != base
