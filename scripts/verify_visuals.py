#!/usr/bin/env python3
"""Verify scryops article visuals.

Run from the repo root after adding/editing figures:

    python3 scripts/verify_visuals.py [content/articles/my-article.md ...]

With no arguments it scans every markdown file under content/. Checks:
  1. every {{< obs-* >}} / {{< mermaid >}} reference resolves to a shortcode file
  2. each referenced obs-*.html SVG is well-formed XML and each HTML fragment has balanced tags
  3. normalize-tags.py passes (tag casing)
  4. figure labels don't trip the OTel correctness traps (see CLAUDE.md > OTel Correctness Gotchas)

Exit code is non-zero if any hard check fails. OTel hits are warnings (judgment needed).
Standard library only.
"""
import sys, os, re, glob, subprocess
import xml.dom.minidom as minidom
from html.parser import HTMLParser
import mermaid_lib

SHORTCODE_DIR = os.path.join("themes", "scryops", "layouts", "shortcodes")
VOID = {"br", "hr", "img", "input", "meta", "link", "rect", "line", "circle",
        "polyline", "polygon", "path", "use", "stop", "ellipse", "source"}
NAMED_ENTS = {"&rsquo;": "'", "&lsquo;": "'", "&rdquo;": '"', "&ldquo;": '"',
              "&mdash;": "-", "&ndash;": "-", "&middot;": ".", "&times;": "x",
              "&amp;": "&amp;", "&nbsp;": " ", "&hellip;": "...", "&deg;": " "}

GREEN, RED, YEL, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
def ok(m):   print(f"{GREEN}OK{OFF}   {m}")
def fail(m): print(f"{RED}FAIL{OFF} {m}")
def warn(m): print(f"{YEL}WARN{OFF} {m}")


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.error = None
    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        pass
    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.error = f"unexpected </{tag}>"


def check_wellformed(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"<svg.*?</svg>", txt, re.S)
    if m:
        test = m.group(0)
        for k, v in NAMED_ENTS.items():
            test = test.replace(k, v)
        test = re.sub(r"&(?!#?\w+;)", "&amp;", test)
        try:
            minidom.parseString(test)
        except Exception as e:
            return False, f"SVG not well-formed XML: {e}"
    b = Balance()
    b.feed(txt)
    if b.error:
        return False, b.error
    leftover = [t for t in b.stack if t not in ("style",)]
    if leftover:
        return False, f"unbalanced tags, open at EOF: {leftover}"
    return True, "well-formed"


OTEL_PATTERNS = [
    (re.compile(r"jaeger\s+exporter|exporter\s*[:=]\s*jaeger\b", re.I),
     "labels a 'jaeger exporter' — removed in v0.85; use otlp/jaeger -> jaeger:4317"),
    (re.compile(r"otel/opentelemetry-collector(?!-contrib)\b"),
     "uses otel/opentelemetry-collector — prefer ...-collector-contrib for OTTL/most configs"),
    (re.compile(r"OTEL_SERVICE_VERSION"),
     "references OTEL_SERVICE_VERSION — no such env var; set service.version as a resource attribute or via OTEL_RESOURCE_ATTRIBUTES"),
    (re.compile(r"routing\s+connector[\s\S]{0,40}affinit", re.I),
     "implies routing connector gives trace-ID affinity — use loadbalancingexporter"),
]
BURN = re.compile(r"14\s*[x×][\s\S]{0,60}\b2\s*h(ours?)?\b", re.I)


def check_otel(path):
    txt = open(path, encoding="utf-8").read()
    hits = [msg for rx, msg in OTEL_PATTERNS if rx.search(txt)]
    if BURN.search(txt):
        hits.append("burn-rate label pairs 14x with '2 hours' — a 14x burn exhausts a 30d budget in ~2.1 days")
    return hits


def shortcode_refs(md):
    txt = open(md, encoding="utf-8").read()
    return re.findall(r"{{<\s*([a-zA-Z0-9_-]+)", txt)


def check_diagram_svgs(articles):
    """Every {{< mermaid >}} block must have a committed, current SVG; warn on orphans."""
    out_dir = os.path.join("themes", "scryops", "assets", "diagrams")
    referenced = set()
    hard = False
    print(f"\n{DIM}— diagram SVG pre-render —{OFF}")
    for md, source in mermaid_lib.iter_mermaid_blocks(articles):
        h = mermaid_lib.diagram_hash(source)
        referenced.add(h)
        if os.path.exists(os.path.join(out_dir, f"{h}.svg")):
            ok(f"{md} [{h}]: SVG present")
        else:
            fail(f"{md} [{h}]: missing SVG — run scripts/render-diagrams.py")
            hard = True
    # orphan check only meaningful on a full scan (no file args)
    if len(sys.argv) <= 1 and os.path.isdir(out_dir):
        for svg in glob.glob(os.path.join(out_dir, "*.svg")):
            h = os.path.splitext(os.path.basename(svg))[0]
            if h not in referenced:
                warn(f"orphan SVG {svg} — no diagram references it (safe to git rm)")
    return hard


def main():
    if not os.path.isdir(SHORTCODE_DIR):
        fail(f"run me from the repo root — {SHORTCODE_DIR} not found")
        return 2
    articles = sys.argv[1:] or glob.glob("content/**/*.md", recursive=True)
    hard_fail = False
    checked_files = set()

    print(f"{DIM}— reference resolution & well-formedness —{OFF}")
    for md in articles:
        if not os.path.exists(md):
            fail(f"{md}: not found"); hard_fail = True; continue
        for name in shortcode_refs(md):
            if name in ("mermaid",) or not name.startswith("obs-"):
                continue
            scf = os.path.join(SHORTCODE_DIR, f"{name}.html")
            if not os.path.exists(scf):
                fail(f"{md}: {{{{< {name} >}}}} -> no shortcode file {scf}"); hard_fail = True
                continue
            if scf in checked_files:
                continue
            checked_files.add(scf)
            good, msg = check_wellformed(scf)
            (ok if good else fail)(f"{name}.html: {msg}")
            hard_fail = hard_fail or not good

    if not checked_files:
        warn("no obs-* shortcodes referenced in the given file(s)")

    print(f"\n{DIM}— OTel correctness (warnings) —{OFF}")
    any_otel = False
    for scf in sorted(checked_files):
        for msg in check_otel(scf):
            warn(f"{os.path.basename(scf)}: {msg}"); any_otel = True
    if not any_otel:
        ok("no OTel correctness red flags in referenced figures")

    print(f"\n{DIM}— tag casing —{OFF}")
    tagscript = os.path.join("scripts", "normalize-tags.py")
    if os.path.exists(tagscript):
        r = subprocess.run([sys.executable, tagscript], capture_output=True, text=True)
        print((r.stdout + r.stderr).strip() or "(no output)")
        if r.returncode != 0:
            hard_fail = True
    else:
        warn(f"{tagscript} not found — skipping")

    if check_diagram_svgs(articles):
        hard_fail = True

    print()
    if hard_fail:
        fail("verification FAILED — fix the items above")
        return 1
    ok("all hard checks passed" + (" (review OTel warnings above)" if any_otel else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
