"""Shared helpers for share cards (og:image / twitter:image).

Standard library only: verify_visuals.py imports this in CI, where Pillow and
PyYAML are not installed. render-cards.py adds the drawing on top.

A card's identity is a hash of the raw frontmatter lines that feed it (title,
tags, excerpt, the optional `card:` block) plus RENDER_VERSION. The hash is
stored in the PNG itself (a tEXt chunk), so a stale card is detectable without
re-rendering anything.
"""
import glob, hashlib, os, re, struct

SECTIONS = {"articles": "ARTICLE", "guides": "GUIDE", "howtos": "HOW-TO", "qa": "Q&A"}
OUT_DIR = os.path.join("static", "cards")
DEFAULT_CARD = os.path.join(OUT_DIR, "default.png")
HASH_KEY = "scryops-card"
# Bump when the card layout changes, so every committed card reads as stale.
RENDER_VERSION = "2"


def frontmatter(md_path):
    """Return the raw YAML frontmatter text (between the first two '---' lines)."""
    text = open(md_path, encoding="utf-8").read()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    return m.group(1) if m else ""


def raw_field(fm, key):
    """The raw text of a top-level key, including any indented continuation lines."""
    lines, out, grab = fm.split("\n"), [], False
    for line in lines:
        if re.match(rf"^{re.escape(key)}\s*:", line):
            grab = True
            out.append(line)
            continue
        if grab:
            if line.startswith((" ", "\t", "-")) and line.strip():
                out.append(line)
            else:
                break
    return "\n".join(out)


def is_published(fm):
    return not re.search(r"^draft\s*:\s*true\s*$", fm, re.M)


def pages():
    """(section, stem, md_path) for every published page that gets its own card."""
    for section in SECTIONS:
        for md in sorted(glob.glob(os.path.join("content", section, "*.md"))):
            stem = os.path.splitext(os.path.basename(md))[0]
            if stem == "_index":
                continue
            if is_published(frontmatter(md)):
                yield section, stem, md


def card_path(section, stem):
    return os.path.join(OUT_DIR, section, f"{stem}.png")


def input_hash(section, stem, md_path):
    fm = frontmatter(md_path)
    parts = [RENDER_VERSION, section, stem] + [raw_field(fm, k) for k in ("title", "tags", "excerpt", "card")]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def default_hash():
    return hashlib.sha256(f"{RENDER_VERSION}\x1fdefault".encode()).hexdigest()[:16]


def read_png_hash(png_path):
    """Return the HASH_KEY tEXt value stored in a PNG, or None."""
    try:
        data = open(png_path, "rb").read()
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i = 8
    while i + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + length]
        if ctype == b"tEXt":
            key, _, val = body.partition(b"\x00")
            if key.decode("latin-1") == HASH_KEY:
                return val.decode("latin-1")
        if ctype == b"IEND":
            break
        i += 12 + length
    return None


def stale_cards():
    """List of (path, reason) for cards that are missing or out of date."""
    problems = []
    if read_png_hash(DEFAULT_CARD) != default_hash():
        problems.append((DEFAULT_CARD, "missing" if not os.path.exists(DEFAULT_CARD) else "stale"))
    for section, stem, md in pages():
        path = card_path(section, stem)
        if not os.path.exists(path):
            problems.append((path, f"missing for {md}"))
        elif read_png_hash(path) != input_hash(section, stem, md):
            problems.append((path, f"stale for {md}"))
    return problems


def orphan_cards():
    """Committed cards whose page is gone or no longer published."""
    want = {card_path(s, st) for s, st, _ in pages()} | {DEFAULT_CARD}
    return [p for p in glob.glob(os.path.join(OUT_DIR, "**", "*.png"), recursive=True) if p not in want]
