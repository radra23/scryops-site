"""Tests for the LinkedIn announce pipeline (linkedin_lib.py + linkedin-announce.py).

Standard library only apart from pytest, matching CI. Network calls are
replaced, so nothing here talks to LinkedIn or scryops.dev.

Run: pytest scripts/test_linkedin_lib.py
"""
import datetime as dt
import importlib.util
import json
import os

import pytest
import linkedin_lib as ll

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = dt.date(2026, 10, 12)


def write_md(path, fm, body="Body.\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\n{fm}\n---\n\n{body}")


def page_fm(title="A Title", date="2026-10-01", draft="false", extra=""):
    fm = (f'title: "{title}"\ndate: {date}\ndraft: {draft}\n'
          'excerpt: "An excerpt (with parens) and a #hash."\nreadtime: 5\n'
          'tags: ["OpenTelemetry", "Best Practices", "CI/CD", "Tracing"]')
    return fm + ("\n" + extra if extra else "")


def card(section, stem):
    path = os.path.join("static", "cards", section, f"{stem}.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(b"\x89PNG")


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def announce():
    spec = importlib.util.spec_from_file_location("announce", os.path.join(HERE, "linkedin-announce.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- frontmatter ----------

def test_scalar_handles_quotes_blocks_and_absence(site):
    write_md("content/guides/a.md", page_fm(extra='linkedin_text: |\n  Line one.\n\n  Line two #Tag.\nweight: 3'))
    fm = ll.card_lib.frontmatter("content/guides/a.md")
    assert ll.scalar(fm, "title") == "A Title"
    assert ll.scalar(fm, "draft") == "false"
    assert ll.scalar(fm, "linkedin_text") == "Line one.\n\nLine two #Tag."
    assert ll.scalar(fm, "slug") is None


def test_scalar_unescapes_double_quoted_strings(site):
    write_md("content/qa/q.md", 'title: "Say \\"hi\\""\ndate: 2026-10-01\ndraft: false')
    assert ll.scalar(ll.card_lib.frontmatter("content/qa/q.md"), "title") == 'Say "hi"'


def test_tag_list_inline_and_block(site):
    write_md("content/guides/a.md", page_fm())
    write_md("content/guides/b.md", 'title: "B"\ndate: 2026-10-01\ntags:\n  - "SLOs"\n  - Alerting')
    assert ll.tag_list(ll.card_lib.frontmatter("content/guides/a.md")) == ["OpenTelemetry", "Best Practices", "CI/CD", "Tracing"]
    assert ll.tag_list(ll.card_lib.frontmatter("content/guides/b.md")) == ["SLOs", "Alerting"]


def test_page_url_respects_url_and_slug():
    assert ll.page_url("", "articles", "foo") == "https://scryops.dev/articles/foo/"
    assert ll.page_url('slug: "Bar"', "guides", "foo") == "https://scryops.dev/guides/bar/"
    assert ll.page_url('url: "/alert-body-template/"', "howtos", "x") == "https://scryops.dev/alert-body-template/"


def test_load_pages_skips_drafts_and_index_and_sorts_oldest_first(site):
    write_md("content/articles/new.md", page_fm(date="2026-10-10"))
    write_md("content/articles/old.md", page_fm(date="2026-09-01"))
    write_md("content/articles/draft.md", page_fm(draft="true"))
    write_md("content/articles/_index.md", 'title: "Articles"')
    write_md("content/articles/off.md", page_fm(extra="linkedin: false"))
    card("articles", "old")
    pages = ll.load_pages()
    assert [p.key for p in pages] == ["articles/old", "articles/off", "articles/new"]
    assert pages[0].card.endswith("static/cards/articles/old.png") and pages[2].card == ""
    assert pages[1].enabled is False


# ---------- post text ----------

def test_hashtags_are_cleaned_capped_and_deduplicated():
    assert ll.hashtag("Best Practices") == "BestPractices"
    assert ll.hashtag("CI/CD") == "CICD"
    assert ll.hashtag("3D") == ""
    p = ll.Page("a/b", "articles", "b", "x", "T", "", TODAY, ["SLOs", "slos", "AI", "eBPF", "Tracing"], "https://scryops.dev/a/b/")
    assert ll.plain_text(p).endswith("#SLOs #AI #eBPF")


def test_little_text_escapes_reserved_characters_but_keeps_hashtags():
    out = ll.to_little_text("Costs (really) drop by 50% @ scale_ok #OpenTelemetry, see https://x.dev/a#frag")
    assert "\\(really\\)" in out and "\\@" in out and "scale\\_ok" in out
    assert "{hashtag|\\#|OpenTelemetry}" in out
    assert "a\\#frag" in out                       # a URL fragment is not a hashtag


def test_commentary_has_lead_excerpt_link_and_tags(site):
    write_md("content/howtos/h.md", page_fm(title="Do the thing"))
    p = ll.load_pages()[0]
    text = ll.plain_text(p)
    assert text.startswith("New how-to on scryops: Do the thing\n\n")
    assert "Read it here: https://scryops.dev/howtos/h/" in text
    assert text.endswith("#OpenTelemetry #BestPractices #CICD")
    assert "—" not in text


def test_custom_text_wins(site):
    write_md("content/qa/q.md", page_fm(extra='linkedin_text: "My own words. #SRE"'))
    p = ll.load_pages()[0]
    assert ll.commentary(p) == "My own words. {hashtag|\\#|SRE}"


def test_commentary_over_limit_raises():
    p = ll.Page("a/b", "articles", "b", "x", "T", "", TODAY, custom_text="x" * 3001)
    with pytest.raises(ValueError):
        ll.commentary(p)


def test_payload_shape():
    p = ll.Page("a/b", "articles", "b", "x", "Title", "Ex", TODAY, [], "https://scryops.dev/articles/b/")
    body = ll.post_payload(p, "urn:li:person:abc", "urn:li:image:1")
    assert body["author"] == "urn:li:person:abc"
    assert body["content"] == {"article": {"source": p.url, "title": "Title", "description": "Ex", "thumbnail": "urn:li:image:1"}}
    assert body["lifecycleState"] == "PUBLISHED" and body["visibility"] == "PUBLIC"
    assert "thumbnail" not in ll.post_payload(p, "urn:li:person:abc")["content"]["article"]


# ---------- ledger ----------

def pages_fixture(site):
    write_md("content/articles/live.md", page_fm(date="2026-10-01"))
    write_md("content/guides/today.md", page_fm(date="2026-10-12"))
    write_md("content/guides/future.md", page_fm(date="2026-11-01"))
    write_md("content/qa/off.md", page_fm(date="2026-10-02", extra="linkedin: false"))
    return ll.load_pages()


def test_baseline_records_only_live_pages(site):
    state = ll.baseline(ll.new_state(), pages_fixture(site), TODAY, "t")
    assert sorted(state["posts"]) == ["articles/live", "guides/today", "qa/off"]
    assert ll.pending(ll.load_pages(), state, TODAY) == []
    assert [p.key for p in ll.scheduled(ll.load_pages(), state, TODAY)] == ["guides/future"]


def test_pending_skips_ledger_opt_outs_and_future(site):
    pages = pages_fixture(site)
    state = ll.new_state()
    ll.record(state, ll.find(pages, "articles/live"), "t", "urn:li:share:1")
    assert [p.key for p in ll.pending(pages, state, TODAY)] == ["guides/today"]
    assert ll.find(pages, "content/guides/future.md").key == "guides/future"
    assert ll.find(pages, "./content/guides/today.md").key == "guides/today"


# ---------- CLI plan / post (network stubbed) ----------

def run(mod, monkeypatch, argv, live=True):
    monkeypatch.setattr(mod, "is_live", lambda url, timeout=15: live)
    monkeypatch.setattr("sys.argv", ["linkedin-announce.py", *argv])
    mod.main()


def outputs(capsys):
    return dict(l.split("=", 1) for l in capsys.readouterr().out.splitlines() if l.startswith(("key=", "state_changed=")))


def test_first_run_is_baseline_only(site, announce, monkeypatch, capsys):
    pages_fixture(site)
    open("state.json", "w").close()
    run(announce, monkeypatch, ["plan", "--state", "state.json", "--today", "2026-10-12"])
    assert outputs(capsys) == {"key": "", "state_changed": "true"}
    assert len(json.load(open("state.json"))["posts"]) == 3


def test_plan_picks_oldest_live_pending(site, announce, monkeypatch, capsys):
    pages = pages_fixture(site)
    write_md("content/howtos/also.md", page_fm(date="2026-10-11"))
    state = ll.baseline(ll.new_state(), pages, dt.date(2026, 10, 1), "t")
    announce.save_state("state.json", state)
    run(announce, monkeypatch, ["plan", "--state", "state.json", "--today", "2026-10-12", "--rounds", "1"])
    assert outputs(capsys)["key"] == "howtos/also"


def test_plan_waits_when_not_live(site, announce, monkeypatch, capsys):
    pages = pages_fixture(site)
    announce.save_state("state.json", ll.baseline(ll.new_state(), pages, dt.date(2026, 10, 1), "t"))
    run(announce, monkeypatch, ["plan", "--state", "state.json", "--today", "2026-10-12", "--rounds", "1"], live=False)
    assert outputs(capsys)["key"] == ""


def test_plan_ref_refuses_repeat_without_again(site, announce, monkeypatch):
    pages = pages_fixture(site)
    state = ll.new_state()
    ll.record(state, ll.find(pages, "articles/live"), "t", "urn:li:share:1")
    announce.save_state("state.json", state)
    with pytest.raises(SystemExit):
        run(announce, monkeypatch, ["plan", "--state", "state.json", "--ref", "content/articles/live.md"])


def test_post_uploads_card_posts_and_records(site, announce, monkeypatch):
    write_md("content/articles/a.md", page_fm())
    card("articles", "a")
    announce.save_state("state.json", ll.new_state())
    calls = []

    def fake_req(self, method, url, body=None, headers=None, raw=None):
        calls.append((method, url.split("?")[0], body))
        if "initializeUpload" in url:
            return 200, {}, {"value": {"uploadUrl": "https://upload.example/x", "image": "urn:li:image:42"}}
        if url.endswith("/rest/posts"):
            return 201, {"x-restli-id": "urn:li:share:99"}, None
        return 201, {}, None

    monkeypatch.setattr(announce.LinkedIn, "_req", fake_req)
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "t")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:me")
    monkeypatch.setenv("LINKEDIN_TOKEN_EXPIRES_AT", "2099-01-01T00:00:00+00:00")
    run(announce, monkeypatch, ["post", "--state", "state.json", "--key", "articles/a"])

    assert [c[0] for c in calls] == ["POST", "PUT", "POST"]
    assert calls[2][2]["content"]["article"]["thumbnail"] == "urn:li:image:42"
    entry = json.load(open("state.json"))["posts"]["articles/a"]
    assert entry["status"] == "announced" and entry["urn"] == "urn:li:share:99"

    calls.clear()   # a rerun is a no-op
    run(announce, monkeypatch, ["post", "--state", "state.json", "--key", "articles/a"])
    assert calls == []


def test_post_refuses_expired_token(site, announce, monkeypatch):
    write_md("content/articles/a.md", page_fm())
    announce.save_state("state.json", ll.new_state())
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "t")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:me")
    monkeypatch.setenv("LINKEDIN_TOKEN_EXPIRES_AT", "2020-01-01T00:00:00Z")
    with pytest.raises(SystemExit, match="expired"):
        run(announce, monkeypatch, ["post", "--state", "state.json", "--key", "articles/a"])
