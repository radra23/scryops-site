#!/usr/bin/env python3
"""
normalize-tags.py
Ensures tag casing in all content frontmatter matches the canonical list.

Usage:
  python3 scripts/normalize-tags.py          # check only, exits 1 on any issue
  python3 scripts/normalize-tags.py --fix    # auto-correct casing in-place
  python3 scripts/normalize-tags.py --list   # print the canonical tag list

To add a new canonical tag, append it to CANONICAL_TAGS below.
"""

import sys
import re
from pathlib import Path

# ── Single source of truth for all valid tags ────────────────────────────────
CANONICAL_TAGS = [
    "AI",
    "Alerting",
    "Best Practices",
    "Collector",
    "Cost",
    "Debugging",
    "eBPF",
    "GDPR",
    "Grafana",
    "How-to",
    "Jaeger",
    "Kubernetes",
    "Logs",
    "Metrics",
    "Monitoring",
    "Observability",
    "On-Call",
    "OpenTelemetry",
    "Operations",
    "OTLP",
    "Philosophy",
    "Privacy",
    "Profiling",
    "Prometheus",
    "Python",
    "Reliability",
    "Sampling",
    "Security",
    "SLOs",
    "Structured Logging",
    "Tracing",
]
# ─────────────────────────────────────────────────────────────────────────────

# Case-insensitive lookup: "opentelemetry" → "OpenTelemetry"
_LOOKUP = {t.lower(): t for t in CANONICAL_TAGS}


def canonical(tag):
    """Return canonical form of tag, or None if unknown."""
    return _LOOKUP.get(tag.strip().lower())


def process_file(path, fix):
    """
    Parse frontmatter tags, compare against canonical list.
    Returns list of issue strings. Writes corrected file if fix=True.
    """
    text = path.read_text(encoding="utf-8")

    # Match YAML frontmatter block
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return []

    fm = fm_match.group(1)

    # Match inline tags array: tags: ["Foo", "Bar"]
    tags_match = re.search(r"^(tags:\s*\[)([^\]]*?)(\])", fm, re.MULTILINE)
    if not tags_match:
        return []

    prefix, raw_str, suffix = tags_match.group(1), tags_match.group(2), tags_match.group(3)
    raw_tags = [t.strip().strip('"').strip("'") for t in raw_str.split(",") if t.strip()]

    issues = []
    new_tags = []

    for tag in raw_tags:
        c = canonical(tag)
        if c is None:
            issues.append(f"  UNKNOWN  '{tag}'")
            new_tags.append(tag)
        elif c != tag:
            issues.append(f"  CASING   '{tag}' → '{c}'")
            new_tags.append(c)
        else:
            new_tags.append(tag)

    if fix and new_tags != raw_tags:
        fixed_str = ", ".join(f'"{t}"' for t in new_tags)
        new_fm = fm[: tags_match.start(2)] + fixed_str + fm[tags_match.end(2):]
        new_text = text[: fm_match.start(1)] + new_fm + text[fm_match.end(1):]
        path.write_text(new_text, encoding="utf-8")

    return issues


def main():
    args = sys.argv[1:]

    if "--list" in args:
        print("Canonical tags:")
        for t in sorted(CANONICAL_TAGS, key=str.lower):
            print(f"  {t}")
        sys.exit(0)

    fix = "--fix" in args
    content_root = Path(__file__).parent.parent / "content"

    all_issues = {}
    for md_file in sorted(content_root.rglob("*.md")):
        issues = process_file(md_file, fix=fix)
        if issues:
            all_issues[md_file] = issues

    if not all_issues:
        print("✓ All tags match canonical casing.")
        sys.exit(0)

    action = "Fixed" if fix else "Found"
    for path, issues in all_issues.items():
        rel = path.relative_to(content_root.parent)
        print(f"\n{action} issues in {rel}:")
        for issue in issues:
            print(issue)

    if fix:
        print("\n✓ All casing issues corrected.")
        sys.exit(0)
    else:
        print("\nRun with --fix to auto-correct, or add new tags to CANONICAL_TAGS in scripts/normalize-tags.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
