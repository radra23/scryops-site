#!/usr/bin/env python3
"""Render 1200x630 share cards (og:image / twitter:image) for scryops.

    python3 scripts/render-cards.py           # render missing or stale cards
    python3 scripts/render-cards.py --all     # re-render every card
    python3 scripts/render-cards.py --prune   # also delete orphaned cards

One card per published article/guide/how-to/Q&A, written to
static/cards/<section>/<file-stem>.png, plus static/cards/default.png for the
homepage and list pages. Each card: lens + wordmark, a SECTION · TAG eyebrow,
the title, and either the excerpt (2 lines max) or an evidence panel from
frontmatter (4 rows max). Secondary text is sized for a phone feed, where a
card shows at ~0.29x: eyebrow 28px, panel rows and excerpt 32px (~8-9pt).

    card:
      title: "Green dashboard, broken request"   # optional, see below
      panel:
        - {key: error_rate, value: "0.3%", state: ok}
        - {key: checkout.total, value: "$0.00", state: warn, label: "200 OK, no error"}

card.title (optional) replaces the page title on the card only; og:title keeps
the real title, which most apps print under the image anyway. The headline fits
at 60px when the title takes 3 lines or fewer (~12.5pt in a ~250pt chat bubble)
and only drops to 54/48/44/40px (down to ~8pt there) when it can't. So for a
3-line title card.title is polish, a quicker read with room for the excerpt;
for a title too long for 3 lines at 60px it keeps the headline large.

state is ok | warn | error (glyph ● ▲ ■, never colour alone); label defaults to
OK / WARN / ERROR. A dashed rule separates the first non-ok row from the ok rows.

Colours are read from telemetry.css (dark theme :root), fonts from the
self-hosted woff2 files. Needs Pillow, fontTools (+brotli) and PyYAML; the PNGs
are committed, so CI and Hugo never need them. verify_visuals.py fails on a
missing or stale card.
"""
import io, os, re, sys
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
from fontTools.ttLib import TTFont
import yaml
import card_lib

W, H, S = 1200, 630, 2          # final size; drawn at S x and downsampled
M = 80                          # outer margin
FONT_DIR = os.path.join("themes", "scryops", "static", "fonts", "vendor")
CSS = os.path.join("themes", "scryops", "assets", "css", "telemetry.css")


def tokens():
    """Dark-theme colour tokens from the first :root block of telemetry.css."""
    css = open(CSS, encoding="utf-8").read()
    root = re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)
    t = dict(re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})", root))
    need = ("bg", "surface", "frame", "border", "heading", "text", "muted", "green", "warn", "danger")
    missing = [k for k in need if k not in t]
    if missing:
        sys.exit(f"telemetry.css :root is missing {missing}")
    return {k: t[k] for k in need}


_fonts = {}
def font(name, size):
    """A self-hosted woff2 face, converted to TTF in memory for FreeType."""
    if name not in _fonts:
        f = TTFont(os.path.join(FONT_DIR, name))
        f.flavor = None
        buf = io.BytesIO(); f.save(buf)
        _fonts[name] = buf.getvalue()
    return ImageFont.truetype(io.BytesIO(_fonts[name]), size * S)

PLEX_SB, PLEX_MD, PLEX = "ibm-plex-mono-600.woff2", "ibm-plex-mono-500.woff2", "ibm-plex-mono-400.woff2"
DOTO, PIXELIFY, READ = "doto-900.woff2", "pixelify-sans-scry-700.1fe9f8f9.woff2", "atkinson-hyperlegible-400.woff2"

# The lens: 16-cell disc, dotted left half (scry), solid right half (ops),
# rounded 4x4 void at the centre. Same cells as partials/brand-mark.html.
_DISC = {(x, y) for y in range(16) for x in range(16) if (x - 7.5) ** 2 + (y - 7.5) ** 2 <= 6.4 ** 2}
_VOID = {(x, y) for x in range(6, 10) for y in range(6, 10)} - {(6, 6), (9, 6), (6, 9), (9, 9)}
LENS = _DISC - _VOID


def draw_lens(d, x0, y0, cell, ink, green):
    c = cell * S
    for x, y in LENS:
        px, py = (x0 * S + x * c, y0 * S + y * c)
        if x < 8:
            r = 0.4 * c
            d.ellipse([px + c / 2 - r, py + c / 2 - r, px + c / 2 + r, py + c / 2 + r], fill=ink)
        else:
            d.rectangle([px, py, px + c - 1, py + c - 1], fill=green)


def text(d, xy, s, f, fill, anchor="la", track=0):
    """Draw text at final-size coordinates; optional letter-spacing in px."""
    x, y = xy[0] * S, xy[1] * S
    if not track:
        d.text((x, y), s, font=f, fill=fill, anchor=anchor)
        return
    width = sum(f.getlength(ch) for ch in s) + track * S * (len(s) - 1)
    if anchor[0] == "r":
        x -= width
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill, anchor="l" + anchor[1])
        x += f.getlength(ch) + track * S


def wrap(s, f, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) <= width * S or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_headline(title, max_lines):
    for size in (60, 54, 48, 44, 40):
        f = font(PLEX_SB, size)
        lines = wrap(title, f, W - 2 * M)
        if len(lines) <= max_lines:
            return f, size, lines
    lines = wrap(title, f, W - 2 * M)[:max_lines]
    lines[-1] = lines[-1].rstrip(".,;: ") + "…"
    return f, size, lines


def header(d, t, eyebrow):
    draw_lens(d, M, 50, 3, t["heading"], t["green"])             # 48px lens
    fy, x = 74, M + 48 + 16
    scry, ops = font(DOTO, 38), font(PIXELIFY, 38)
    d.text((x * S, fy * S), "scry", font=scry, fill=t["heading"], anchor="lm")
    d.text((x * S + scry.getlength("scry"), fy * S), "ops", font=ops, fill=t["green"], anchor="lm")
    text(d, (W - M, fy), eyebrow, font(PLEX_MD, 28), t["muted"], anchor="rm", track=2)


GLYPH = {"ok": "green", "warn": "warn", "error": "danger"}
LABEL = {"ok": "OK", "warn": "WARN", "error": "ERROR"}


def glyph(d, kind, cx, cy, colour):
    r = 9 * S
    cx, cy = cx * S, cy * S
    if kind == "ok":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)
    elif kind == "warn":
        d.polygon([(cx, cy - r - 1 * S), (cx + r + 1 * S, cy + r), (cx - r - 1 * S, cy + r)], fill=colour)
    else:
        d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=colour)


def panel(d, t, rows):
    row_h, pad, gap = 50, 28, 18
    first_alert = next((i for i, r in enumerate(rows) if r["state"] != "ok"), None)
    divider = first_alert not in (None, 0)
    h = pad * 2 + row_h * len(rows) + (gap if divider else 0)
    top, bottom = H - 44 - h, H - 44
    d.rounded_rectangle([M * S, top * S, (W - M) * S, bottom * S], radius=10 * S,
                        fill=t["surface"], outline=t["frame"], width=S)
    y = top + pad + row_h / 2
    for i, r in enumerate(rows):
        if divider and i == first_alert:
            ry = (y - row_h / 2 + gap / 2) * S                      # middle of the gap
            for x in range((M + 28) * S, (W - M - 28) * S, 8 * S):  # dashed rule
                d.line([(x, ry), (x + 4 * S, ry)], fill=t["border"], width=S)
            y += gap
        state = r["state"]
        col = t[GLYPH[state]]
        alert = state != "ok"
        text(d, (M + 30, y), r["key"], font(PLEX, 32), t["text"], anchor="lm")
        text(d, (M + 340, y), r["value"], font(PLEX, 32), col if alert else t["heading"], anchor="lm")
        glyph(d, state, M + 532, y, col)
        label = (r.get("label") or LABEL[state]).upper()
        text(d, (M + 558, y), label, font(PLEX_SB if alert else PLEX, 32), col, anchor="lm")
        y += row_h
    return top


def render(eyebrow, title, excerpt=None, rows=None, accent_word=None):
    t = tokens()
    img = Image.new("RGB", (W * S, H * S), t["bg"])
    d = ImageDraw.Draw(img)
    header(d, t, eyebrow)
    f, size, lines = fit_headline(title, 2 if rows else 3)
    lh, y = round(size * 1.18), 140
    el = []
    if not rows and excerpt:
        ef = font(READ, 32)
        el = wrap(excerpt, ef, W - 2 * M)
        cap = 2                                                  # 32px excerpt: two lines at most
        if len(el) > cap:
            el = el[:cap]; el[-1] = el[-1].rstrip(".,;: ") + "…"
        # centre headline + excerpt in the space below the header (y≈120..586)
        block = len(lines) * lh + 24 + 46 * len(el)
        y = max(140, round(120 + (466 - block) / 2))
    for line in lines:
        if accent_word and accent_word in line:                     # default card: green "understanding"
            pre, _, post = line.partition(accent_word)
            x = M * S
            for part, col in ((pre, t["heading"]), (accent_word, t["green"]), (post, t["heading"])):
                d.text((x, y * S), part, font=f, fill=col); x += f.getlength(part)
        else:
            text(d, (M, y), line, f, t["heading"])
        y += lh
    if rows:
        panel(d, t, rows)
    else:
        y += 24
        for line in el:
            text(d, (M, y), line, ef, t["muted"]); y += 46
    # Outer edge: a 3px --frame border, the design system's container edge. The
    # dark card sits at ~1.1:1 on dark-mode feeds; --frame lifts the outline to
    # ~1.6-2.0:1 there and vanishes into the card on light feeds. Inset 1px with a
    # 36px radius so apps that round preview corners don't clip it away.
    d.rounded_rectangle([1 * S, 1 * S, (W - 1) * S - 1, (H - 1) * S - 1], radius=36 * S,
                        outline=t["frame"], width=3 * S)
    img = img.resize((W, H), Image.LANCZOS)
    # Downsampling blends the 3px line with its neighbours (#453E33 -> #423C31).
    # Repaint the straight runs at 1x so they are the exact token; the corner
    # arcs keep their 2x anti-aliasing. quantize() reserves the colour.
    d1, r = ImageDraw.Draw(img), 1 + 36
    for k in (1, 2, 3):
        d1.line([(r, k), (W - 1 - r, k)], fill=t["frame"])
        d1.line([(r, H - 1 - k), (W - 1 - r, H - 1 - k)], fill=t["frame"])
        d1.line([(k, r), (k, H - 1 - r)], fill=t["frame"])
        d1.line([(W - 1 - k, r), (W - 1 - k, H - 1 - r)], fill=t["frame"])
    return img


def save(img, path, h):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    info = PngImagePlugin.PngInfo()
    info.add_text(card_lib.HASH_KEY, h)
    quantize(img).save(path, optimize=True, pnginfo=info)


def quantize(img):
    """128-colour palette with --frame reserved as an exact entry.

    An adaptive palette alone rounded the 2px frame from #453E33 to #433C32,
    which cost ~0.05 of edge contrast on dark feeds. Take 127 adaptive colours,
    append the exact frame colour (snapping near-duplicates onto it), then map
    every pixel to the nearest entry: pure frame pixels land on it exactly.
    """
    frame = tuple(int(tokens()["frame"][i:i + 2], 16) for i in (1, 3, 5))
    adaptive = img.quantize(colors=127, dither=Image.Dither.NONE)
    pal = adaptive.getpalette()[:127 * 3]
    # Pillow's nearest-colour lookup can't split a 1-level difference, so an
    # adaptive entry like #453E32 would steal the frame pixels: snap any entry
    # within 4 levels of the frame onto it exactly.
    for i in range(0, len(pal), 3):
        if max(abs(pal[i + c] - frame[c]) for c in range(3)) <= 4:
            pal[i:i + 3] = list(frame)
    pal += list(frame)
    ref = Image.new("P", (1, 1))
    ref.putpalette(pal + [0] * (768 - len(pal)))
    return img.quantize(palette=ref, dither=Image.Dither.NONE)


def page_card(section, stem, md):
    fm = yaml.safe_load(card_lib.frontmatter(md)) or {}
    tags = fm.get("tags") or []
    eyebrow = card_lib.SECTIONS[section] + (f" · {tags[0].upper()}" if tags else "")
    rows = (fm.get("card") or {}).get("panel")
    if rows and len(rows) > 4:
        sys.exit(f"{md}: card.panel has {len(rows)} rows; 4 at most (rows are 32px so they read on a phone)")
    for r in rows or []:
        if r.get("state") not in ("ok", "warn", "error"):
            sys.exit(f"{md}: card.panel state must be ok|warn|error, got {r.get('state')!r}")
    return render(eyebrow, headline(fm, md), fm.get("excerpt"), rows)


def headline(fm, md="page"):
    """The card headline: card.title when set, else the page title."""
    t = (fm.get("card") or {}).get("title")
    if t is None:
        return fm["title"]
    if not isinstance(t, str) or not t.strip():
        sys.exit(f"{md}: card.title must be a non-empty string")
    return t.strip()


def main():
    if not os.path.isdir("content"):
        sys.exit("run me from the repo root")
    force, prune = "--all" in sys.argv, "--prune" in sys.argv
    done = 0
    if force or card_lib.read_png_hash(card_lib.DEFAULT_CARD) != card_lib.default_hash():
        site_desc = re.search(r'^\s*description\s*=\s*"(.*)"', open("hugo.toml", encoding="utf-8").read(), re.M)
        img = render("OBSERVABILITY DECODED", "raw telemetry in. understanding out.",
                     site_desc.group(1) if site_desc else None, accent_word="understanding")
        save(img, card_lib.DEFAULT_CARD, card_lib.default_hash()); done += 1
        print(f"rendered {card_lib.DEFAULT_CARD}")
    for section, stem, md in card_lib.pages():
        path, h = card_lib.card_path(section, stem), card_lib.input_hash(section, stem, md)
        if not force and card_lib.read_png_hash(path) == h:
            continue
        save(page_card(section, stem, md), path, h); done += 1
        print(f"rendered {path}")
    for orphan in card_lib.orphan_cards():
        if prune:
            os.remove(orphan); print(f"removed orphan {orphan}")
        else:
            print(f"orphan {orphan} (re-run with --prune to delete)")
    print(f"{done} card(s) rendered")


if __name__ == "__main__":
    main()
