#!/usr/bin/env python3
"""Self-host the Google font families telemetry.css actually uses.

Fetches the latin subset only (the site is lang="en"; the latin range already
covers em-dashes and curly quotes), downloads each woff2 into the theme, and
emits a fonts.css with local src paths. Idempotent.

Doto (900) and Pixelify Sans (700) are the wordmark's two pixel voices
(--font-pixel-scry / --font-pixel-ops) per the scryops-design DS spec —
Press Start 2P is retained for pages that still name it directly, but new
pixel-voice work uses this pair.
"""
import glob
import hashlib
import os
import re
import subprocess
import sys

THEME = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "themes", "scryops"))
FONT_DIR = os.path.join(THEME, "static/fonts/vendor")
CSS_OUT = os.path.join(THEME, "assets/css/fonts.css")

# Every family telemetry.css uses. Atkinson Hyperlegible is the
# hyperlegible reading-pref face (incl. italic); the other four are the
# display/reading/code/pixel system fonts.
GOOGLE_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=IBM+Plex+Mono:wght@400;500;600"
    "&family=Courier+Prime:wght@400;700"
    "&family=Space+Mono:wght@400;700"
    "&family=Press+Start+2P"
    "&family=Doto:wght@900"
    "&family=Pixelify+Sans:wght@700"
    "&family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400"
    "&display=swap"
)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

# Glyph patches applied after download, keyed by the downloaded filename.
# Pixelify Sans 700 is drawn on a grid of ~88x86-unit pixels split into
# 49/39-unit columns and 51/35-unit rows, and many glyphs are an O-ring whose
# only opening is one 35-unit row (or one 49-unit column). At label sizes
# (10-13px, ~38 units per device pixel even at 2x) that sliver antialiases
# shut: C reads O, 2/3/6/9/B/S read 8, 5 reads S. Each patch moves a sliver's
# edge points one sub-row further apart — onto the next grid line — so every
# aperture is at least a full 86-unit pixel (B is the exception; see below).
# Advance widths are untouched, so no measured label moves. (K keeps its
# 35-unit crotch pinch: shutting it fills a pocket but still reads K.)
#
# The patched cut ships under its own name (OFL: no Reserved Font Name, but a
# modified version still shouldn't pose as the original) with a content hash
# in the filename: static/ isn't fingerprinted and sw.js serves it
# cache-first, so a re-cut at the same URL would never reach returning
# visitors.
_UP_467 = lambda *xs: {(x, 416): (x, 467) for x in xs}    # stub bottom up a row
_DOWN_160 = lambda *xs: {(x, 211): (x, 160) for x in xs}  # stub top down a row
GLYPH_PATCHES = {
    "pixelify-sans-700.woff2": ("pixelify-sans-scry-700.woff2", "Pixelify Sans Scry", {
        # C: open the right side from y=190 to y=440 (was 297..331)
        "C": {(542, 331): (542, 440), (414, 331): (414, 440),
              (414, 297): (414, 190), (542, 297): (542, 190)},
        # G: raise the upper-right stub so the mouth opens above the spur, and
        # widen the counter's passage left of the spur (x188..237 -> ..276)
        "G": {(542, 331): (542, 440), (414, 331): (414, 440),
              (237, 246): (276, 246), (237, 381): (276, 381)},
        # B: stock B is 8 with a 49-unit passage left of the middle bar, so it
        # shuts to 8 — and widened, it reads G. Instead square its left
        # corners like D (P and R square the foot): a stem is what says B,
        # and a shut passage then gives the right answer, two closed bowls.
        "B": {(149, -11): (61, -11), (149, 74): (61, -11),
              (149, 552): (61, 638), (149, 638): (61, 638)},
        # 2 and Z (same outline, different corners): upper-left and
        # lower-right mouths, y381..416 -> ..467 and y211..246 -> 160..
        "two": {**_UP_467(61, 188), **_DOWN_160(414, 542)},
        "Z": {**_UP_467(61, 188), **_DOWN_160(414, 542)},
        # 3: both left mouths
        "three": {**_UP_467(61, 188), **_DOWN_160(61, 188)},
        # S: upper-right and lower-left mouths
        "S": {**_UP_467(414, 542), **_DOWN_160(61, 188)},
        # 6: upper-right mouth; 9: lower-left mouth
        "six": _UP_467(414, 542),
        "nine": _DOWN_160(61, 188),
        # 5: lower-left mouth, and raise the upper-right stub from y331 to
        # S's 467 so the whole upper right opens (y297..467) like a 5's flag —
        # S keeps a one-pixel mouth over a middle bar at 381
        "five": {**_DOWN_160(61, 188),
                 (542, 331): (542, 467), (414, 331): (414, 467)},
    }),
}


def patch_glyphs(blob, family, moves):
    """Return blob with each glyph's on-curve points remapped per `moves`."""
    import io
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
    # Keep upstream's head.modified so the same input gives the same bytes
    # (and the same content-hashed filename) on every run.
    font = TTFont(io.BytesIO(blob), recalcTimestamp=False)
    glyf = font["glyf"]
    for name, remap in moves.items():
        g = glyf[name]
        hits = 0
        for i, pt in enumerate(g.coordinates):
            if tuple(pt) in remap:
                g.coordinates[i] = remap[tuple(pt)]
                hits += 1
        # Upstream redrew the glyph if the points aren't where we expect —
        # fail loudly rather than ship a half-moved outline.
        if hits != len(remap):
            raise SystemExit(f"patch {name}: matched {hits}/{len(remap)} points")
        # Squaring a corner lands two points on one spot; drop the repeat
        # (safe: the font is unhinted, so no instruction indexes points).
        coords, flags, ends, start = [], [], [], 0
        for end in g.endPtsOfContours:
            pts = list(range(start, end + 1))
            for n, i in enumerate(pts):
                if tuple(g.coordinates[i]) != tuple(g.coordinates[pts[n - 1]]):
                    coords.append(tuple(g.coordinates[i]))
                    flags.append(g.flags[i])
            ends.append(len(coords) - 1)
            start = end + 1
        g.coordinates = GlyphCoordinates(coords)
        g.flags = bytearray(flags)
        g.endPtsOfContours = ends
        g.recalcBounds(glyf)
    for rec in font["name"].names:
        if rec.nameID in (1, 3, 4, 16):
            rec.string = rec.toUnicode().replace("Pixelify Sans", family)
        elif rec.nameID == 6:
            rec.string = rec.toUnicode().replace("PixelifySans", family.replace(" ", ""))
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def fetch(url, binary=False):
    # curl, not urllib: this machine's python.org framework build has no
    # local CA bundle wired up (SSLCertVerificationError), while curl uses
    # the system trust store and just works.
    data = subprocess.run(
        ["curl", "-sSL", "--max-time", "30", "-A", UA, url],
        check=True, capture_output=True,
    ).stdout
    return data if binary else data.decode("utf-8")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    os.makedirs(FONT_DIR, exist_ok=True)
    css = fetch(GOOGLE_URL)

    # Walk each @font-face, capturing its optional preceding "/* subset */"
    # comment. Subsetted families (the four system fonts) emit one face per
    # subset — we keep latin only. Atkinson ships a single, unsubsetted face
    # per style (no comment) — keep those too. Italic gets its own filename so
    # it doesn't collide with the normal weight.
    face_re = re.compile(
        r"(?:/\*\s*([\w-]+)\s*\*/\s*)?(@font-face\s*\{[^}]*\})", re.S)
    out_rules = []
    downloaded = {}
    names = {}     # upstream filename -> shipped filename
    for m in face_re.finditer(css):
        subset, body = m.group(1), m.group(2)
        if subset is not None and subset != "latin":
            continue
        fam = re.search(r"font-family:\s*'([^']+)'", body).group(1)
        weight = re.search(r"font-weight:\s*(\d+)", body).group(1)
        style_m = re.search(r"font-style:\s*(\w+)", body)
        style = style_m.group(1) if style_m else "normal"
        url = re.search(r"src:\s*url\(([^)]+)\)", body).group(1)
        suffix = "" if style == "normal" else f"-{style}"
        src_name = f"{slug(fam)}{suffix}-{weight}.woff2"
        if src_name not in names:
            blob = fetch(url, binary=True)
            fname = src_name
            patch = GLYPH_PATCHES.get(src_name)
            if patch:
                blob = patch_glyphs(blob, patch[1], patch[2])
                stem, ext = os.path.splitext(patch[0])
                fname = f"{stem}.{hashlib.sha256(blob).hexdigest()[:8]}{ext}"
                # Drop earlier cuts (unhashed or older hash) of this file.
                for old in glob.glob(os.path.join(FONT_DIR, f"{stem}*{ext}")):
                    if os.path.basename(old) != fname:
                        os.remove(old)
                        print(f"  removed    {os.path.basename(old)}")
            with open(os.path.join(FONT_DIR, fname), "wb") as f:
                f.write(blob)
            names[src_name] = fname
            downloaded[fname] = len(blob)
            print(f"  downloaded {fname:40s} {len(blob)/1024:6.1f} KB")
        fname = names[src_name]
        # body already contains a full "@font-face { ... }" rule; just localize src.
        rule = body.replace(url, f"/fonts/vendor/{fname}").strip()
        out_rules.append(rule)

    header = ("/* Self-hosted fonts. Generated by scripts/selfhost-fonts.py "
              "— do not edit by hand.\n"
              "   No runtime dependency on fonts.googleapis.com. */\n")
    with open(CSS_OUT, "w") as f:
        f.write(header + "\n".join(out_rules) + "\n")

    total = sum(downloaded.values())
    print(f"\n  {len(downloaded)} files, {total/1024:.1f} KB total -> {FONT_DIR}")
    print(f"  wrote {CSS_OUT}")


if __name__ == "__main__":
    sys.exit(main())
