#!/usr/bin/env python3
"""scryops — annual footprint report (permacomputing phase 5).

Measures the built site in public/ and prints an honest, reproducible snapshot
of its page weight — "observability, applied to ourselves." Run after
`hugo --gc --minify`. Sizes are gzipped, since that's ~what a visitor transfers.

    python3 scripts/footprint-report.py            # human summary
    python3 scripts/footprint-report.py --md        # colophon-ready markdown row values

The method is deliberately simple and inspectable: gzip each built file, group
into page HTML vs shared assets (CSS/JS/fonts). No third-party calls.
"""
import gzip
import os
import statistics
import sys

PUBLIC = os.path.join(os.path.dirname(__file__), "..", "public")


def gz(path):
    with open(path, "rb") as f:
        return len(gzip.compress(f.read(), 6))


def kb(n):
    return n / 1024.0


def walk(exts):
    for root, _dirs, files in os.walk(PUBLIC):
        for name in files:
            if name.lower().endswith(exts):
                yield os.path.join(root, name)


def main():
    if not os.path.isdir(PUBLIC):
        sys.exit("public/ not found — run `hugo --gc --minify` first.")

    pages = [gz(p) for p in walk((".html",))]
    css = sum(gz(p) for p in walk((".css",)))
    js = sum(gz(p) for p in walk((".js",)))
    fonts = sum(gz(p) for p in walk((".woff2", ".woff")))

    pages.sort()
    n = len(pages)
    median = statistics.median(pages) if pages else 0
    heaviest = max(pages) if pages else 0
    shared = css + js  # loaded once, cached by fingerprint thereafter

    md = "--md" in sys.argv
    if md:
        print(f"pages={n}")
        print(f"median_kb={kb(median):.1f}")
        print(f"heaviest_kb={kb(heaviest):.1f}")
        print(f"shared_kb={kb(shared):.1f}")
        print(f"fonts_kb={kb(fonts):.1f}")
        return

    print("scry@ops:~$ footprint --year (measured from public/, gzipped)")
    print(f"  pages published    {n}")
    print(f"  median page (html) {kb(median):5.1f} KB")
    print(f"  heaviest page      {kb(heaviest):5.1f} KB")
    print(f"  shared css + js    {kb(shared):5.1f} KB   (cached after first visit)")
    print(f"  fonts (woff2)      {kb(fonts):5.1f} KB   (cached, loaded as used)")
    print("  method: gzip each built file; page = html, shared = css+js. inspectable, no third-party calls.")


if __name__ == "__main__":
    main()
