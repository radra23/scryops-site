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
import os
import re
import subprocess
import sys

THEME = "/Users/jonhdoe/Repository/scryops-site/themes/scryops"
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
# Pixelify Sans 700 draws C as an O with a 34-unit (0.034em) notch on the
# right, and G the same plus a spur — at label sizes (10-13px) the notch is a
# third of a pixel and antialiases shut, so "CLOCK" reads "OLOCK" and "LOGS"
# reads "LOOS". Each patch moves the notch's edge points apart to cut a real
# aperture; advance widths are untouched, so no measured label moves. The
# patched cut ships under its own filename (OFL: no Reserved Font Name, but a
# modified version still shouldn't pose as the original) — which also busts
# sw.js's cache-first static cache for returning visitors.
GLYPH_PATCHES = {
    "pixelify-sans-700.woff2": ("pixelify-sans-scry-700.woff2", "Pixelify Sans Scry", {
        # C: open the right side from y=190 to y=440 (was 297..331)
        "C": {(542, 331): (542, 440), (414, 331): (414, 440),
              (414, 297): (414, 190), (542, 297): (542, 190)},
        # G: raise the upper-right stub so the mouth opens above the spur
        "G": {(542, 331): (542, 440), (414, 331): (414, 440)},
    }),
}


def patch_glyphs(blob, family, moves):
    """Return blob with each glyph's on-curve points remapped per `moves`."""
    import io
    from fontTools.ttLib import TTFont
    font = TTFont(io.BytesIO(blob))
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
        fname = f"{slug(fam)}{suffix}-{weight}.woff2"
        patch = GLYPH_PATCHES.get(fname)
        if patch:
            fname = patch[0]
        dest = os.path.join(FONT_DIR, fname)
        if fname not in downloaded:
            blob = fetch(url, binary=True)
            if patch:
                blob = patch_glyphs(blob, patch[1], patch[2])
            with open(dest, "wb") as f:
                f.write(blob)
            downloaded[fname] = len(blob)
            print(f"  downloaded {fname:40s} {len(blob)/1024:6.1f} KB")
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
