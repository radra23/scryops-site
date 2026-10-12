"""Announce newly published scryops pages on LinkedIn: the pure logic.

Standard library only, like card_lib.py: the workflow runs this in CI without
installing anything. Network calls live in linkedin-announce.py; everything
here is deterministic and covered by scripts/test_linkedin_lib.py.

What counts as "new" is decided by a ledger (announced.json on the
`linkedin-state` branch), not by git diffs. Publishing here usually means
flipping `draft: true` to `false`, sometimes weeks after the file landed, and
a ledger catches that while making reruns idempotent.

Per-page frontmatter knobs (both optional):

    linkedin: false             # never announce this page
    linkedin_text: |            # replace the generated post text
      Your own words. #Hashtags become real LinkedIn hashtags.
"""
import datetime as dt
import os
import re
from dataclasses import dataclass, field

import card_lib

SITE = "https://scryops.dev/"
STATE_VERSION = 1
MAX_COMMENTARY = 3000          # LinkedIn's limit for post text
MAX_HASHTAGS = 3

LEAD = {
    "articles": "New article on scryops",
    "guides": "New guide on scryops",
    "howtos": "New how-to on scryops",
    "qa": "New Q&A on scryops",
}

# Characters LinkedIn's "little text" format reserves in post commentary.
# Unescaped, they silently truncate the post or turn into mentions/templates.
RESERVED = set("\\|{}@[]()<>#*_~")
HASHTAG = re.compile(r"(?<![\w&/\\])#([A-Za-z][A-Za-z0-9]*)")


# ---------- frontmatter ----------

def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner
    return value


def scalar(fm, key):
    """A top-level scalar, a `|`/`>` block, or None when the key is absent."""
    raw = card_lib.raw_field(fm, key)
    if not raw:
        return None
    first = raw.split("\n")[0]
    value = first.split(":", 1)[1].strip()
    if value in ("|", ">", "|-", ">-"):
        # card_lib.raw_field stops at blank lines; a block scalar keeps them.
        lines, grab = [], False
        for line in fm.split("\n"):
            if grab:
                if line.strip() and not line.startswith((" ", "\t")):
                    break
                lines.append(line)
            elif line == first:
                grab = True
        indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        lines = [l[indent:] for l in lines]
        return ("\n" if value.startswith("|") else " ").join(lines).strip()
    return _unquote(value)


def tag_list(fm):
    raw = card_lib.raw_field(fm, "tags")
    if not raw:
        return []
    inline = raw.split(":", 1)[1].strip()
    if inline.startswith("["):
        return [_unquote(t) for t in re.findall(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'|[^,\[\]\s][^,\[\]]*', inline) if t.strip()]
    return [_unquote(l.strip()[1:]) for l in raw.split("\n")[1:] if l.strip().startswith("-")]


@dataclass
class Page:
    key: str                    # "<section>/<stem>", the ledger key
    section: str
    stem: str
    path: str
    title: str
    excerpt: str
    date: dt.date
    tags: list = field(default_factory=list)
    url: str = ""
    card: str = ""
    enabled: bool = True
    custom_text: str = None


def page_url(fm, section, stem, site=SITE):
    explicit = scalar(fm, "url")
    if explicit:
        return site.rstrip("/") + "/" + explicit.strip("/") + "/"
    slug = scalar(fm, "slug") or stem
    return f"{site.rstrip('/')}/{section}/{slug.lower()}/"


def parse_date(value):
    try:
        return dt.date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def load_pages(site=SITE):
    """Every published page that has a share card, oldest first."""
    pages = []
    for section, stem, md in card_lib.pages():
        fm = card_lib.frontmatter(md)
        date = parse_date(scalar(fm, "date"))
        if date is None:
            continue
        card = card_lib.card_path(section, stem)
        pages.append(Page(
            key=f"{section}/{stem}", section=section, stem=stem, path=md,
            title=scalar(fm, "title") or stem, excerpt=scalar(fm, "excerpt") or "",
            date=date, tags=tag_list(fm), url=page_url(fm, section, stem, site),
            card=card if os.path.exists(card) else "",
            enabled=(scalar(fm, "linkedin") or "").lower() != "false",
            custom_text=scalar(fm, "linkedin_text"),
        ))
    pages.sort(key=lambda p: (p.date, p.key))
    return pages


# ---------- post text ----------

def hashtag(tag):
    """'Best Practices' -> 'BestPractices', 'CI/CD' -> 'CICD'; '' if nothing usable."""
    word = re.sub(r"[^A-Za-z0-9]", "", tag)
    return word if word and word[0].isalpha() else ""


def escape(text):
    return "".join("\\" + c if c in RESERVED else c for c in text)


def to_little_text(plain):
    """Escape plain text for the Posts API, keeping #Words as real hashtags."""
    out, pos = [], 0
    for m in HASHTAG.finditer(plain):
        out.append(escape(plain[pos:m.start()]))
        out.append("{hashtag|\\#|" + m.group(1) + "}")
        pos = m.end()
    out.append(escape(plain[pos:]))
    return "".join(out)


def plain_text(page):
    """What the post says, before escaping. Custom text wins when present."""
    if page.custom_text:
        return page.custom_text.strip()
    tags, seen = [], set()
    for t in page.tags:
        h = hashtag(t)
        if h and h.lower() not in seen:
            seen.add(h.lower())
            tags.append("#" + h)
        if len(tags) == MAX_HASHTAGS:
            break
    parts = [f"{LEAD.get(page.section, 'New on scryops')}: {page.title}"]
    if page.excerpt:
        parts.append(page.excerpt)
    parts.append(f"Read it here: {page.url}")
    if tags:
        parts.append(" ".join(tags))
    return "\n\n".join(parts)


def commentary(page):
    text = to_little_text(plain_text(page))
    if len(text) > MAX_COMMENTARY:
        raise ValueError(f"{page.key}: post text is {len(text)} chars, LinkedIn allows {MAX_COMMENTARY}")
    return text


def post_payload(page, author, image_urn=None):
    article = {"source": page.url, "title": page.title}
    if page.excerpt:
        article["description"] = page.excerpt
    if image_urn:
        article["thumbnail"] = image_urn
    return {
        "author": author,
        "commentary": commentary(page),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {"article": article},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


# ---------- ledger ----------

def new_state():
    return {"version": STATE_VERSION, "posts": {}}


def baseline(state, pages, today, at):
    """First run: record everything already live so the backlog is never posted."""
    for p in pages:
        if p.date <= today and p.key not in state["posts"]:
            state["posts"][p.key] = {"status": "baseline", "at": at, "url": p.url}
    return state


def record(state, page, at, urn):
    state["posts"][page.key] = {"status": "announced", "at": at, "url": page.url, "urn": urn}
    return state


def pending(pages, state, today):
    """Pages to announce, oldest first: published, dated today or earlier, not opted out, not in the ledger."""
    return [p for p in pages
            if p.enabled and p.date <= today and p.key not in state["posts"]]


def scheduled(pages, state, today):
    return [p for p in pages if p.enabled and p.date > today and p.key not in state["posts"]]


def find(pages, ref):
    """Look a page up by ledger key or content path (for manual runs)."""
    ref = ref.strip().lstrip("./")
    for p in pages:
        if ref in (p.key, p.path, p.path.replace(os.sep, "/")):
            return p
    return None
