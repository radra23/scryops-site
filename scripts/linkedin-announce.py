#!/usr/bin/env python3
"""Announce newly published scryops pages on LinkedIn.

    python3 scripts/linkedin-announce.py plan --state announced.json
    python3 scripts/linkedin-announce.py plan --state announced.json --ref content/guides/foo.md
    python3 scripts/linkedin-announce.py post --state announced.json --key guides/foo [--dry-run]

Run by .github/workflows/linkedin.yml; the logic lives in linkedin_lib.py.

plan  picks the next page to announce (oldest first, one per run, only once
      its URL answers 200 on the live site) and writes `key=` and
      `state_changed=` to $GITHUB_OUTPUT plus a preview to the job summary.
      With no ledger yet it records every live page as a baseline and
      announces nothing, so turning this on never floods the feed.
post  uploads the page's share card, creates the post, and records it.

Environment for post: LINKEDIN_ACCESS_TOKEN, LINKEDIN_AUTHOR_URN, and
optionally LINKEDIN_API_VERSION (YYYYMM) and LINKEDIN_TOKEN_EXPIRES_AT (ISO).
Standard library only.
"""
import argparse, datetime as dt, json, os, sys, time
import urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import linkedin_lib as ll

API = "https://api.linkedin.com"
DEFAULT_API_VERSION = "202608"
UA = "scryops-linkedin-announce/1 (+https://scryops.dev)"
REAUTH = "Re-run scripts/linkedin-auth.py locally to issue a new token."


# ---------- io helpers ----------

def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_state(path):
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, encoding="utf-8") as f:
        state = json.load(f)
    if state.get("version") != ll.STATE_VERSION:
        sys.exit(f"{path}: unsupported ledger version {state.get('version')!r}")
    return state


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def gh_output(**kv):
    out = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in kv.items()]
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def summary(md):
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    else:
        print(md)


def is_live(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def preview(page, heading):
    text = ll.plain_text(page)
    quoted = "\n".join("> " + l if l else ">" for l in text.split("\n"))
    card = f"`{page.card}`" if page.card else "_none, posting without a thumbnail_"
    return (f"### {heading}\n\n**[{page.title}]({page.url})** (`{page.path}`)\n\n"
            f"{quoted}\n\nPreview image: {card}\n")


# ---------- plan ----------

def cmd_plan(args):
    pages = ll.load_pages()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    state = load_state(args.state)
    changed = False

    if state is None:
        state = ll.baseline(ll.new_state(), pages, today, now_iso())
        changed = True
        save_state(args.state, state)
        summary(f"## LinkedIn: baseline recorded\n\nNo ledger yet, so the {len(state['posts'])} pages "
                "already live were recorded as baseline and nothing was posted. Pages published from now "
                "on get announced. To announce one specific page anyway, run this workflow manually "
                "with its path.\n")
        if not args.ref:
            gh_output(key="", state_changed="true")
            return

    if args.ref:
        page = ll.find(pages, args.ref)
        if page is None:
            sys.exit(f"No published page matches {args.ref!r} (drafts and pages without a card are excluded).")
        prior = state["posts"].get(page.key, {})
        if prior.get("status") == "announced" and not args.again:
            sys.exit(f"{page.key} was already announced at {prior.get('at')} ({prior.get('urn')}). "
                     "Pass again=true to post it a second time.")
        if not args.no_live_check and not is_live(page.url):
            sys.exit(f"{page.url} is not live yet (no 200). Deploy first.")
        summary(preview(page, "LinkedIn: manual announcement"))
        gh_output(key=page.key, state_changed=str(changed).lower())
        return

    queue = ll.pending(pages, state, today)
    later = ll.scheduled(pages, state, today)
    chosen = None
    for attempt in range(max(1, args.rounds)):
        for page in queue:
            if args.no_live_check or is_live(page.url):
                chosen = page
                break
        if chosen or not queue or attempt == args.rounds - 1:
            break
        time.sleep(args.wait)

    if chosen:
        rest = len(queue) - 1
        note = f"\n_{rest} more page(s) queued; one is announced per run._\n" if rest else ""
        summary(preview(chosen, "LinkedIn: ready to announce (waiting for approval)") + note)
    else:
        lines = ["## LinkedIn: nothing to announce\n"]
        if queue:
            lines.append("Pending but not live yet: " + ", ".join(f"`{p.key}`" for p in queue))
        if later:
            lines.append("Future-dated (Hugo builds them after their date and a deploy): "
                         + ", ".join(f"`{p.key}` ({p.date})" for p in later))
        summary("\n\n".join(lines) + "\n")
    gh_output(key=chosen.key if chosen else "", state_changed=str(changed).lower())


# ---------- post ----------

class LinkedIn:
    def __init__(self, token, version):
        self.token, self.version = token, version

    def _req(self, method, url, body=None, headers=None, raw=None):
        h = {"Authorization": f"Bearer {self.token}", "User-Agent": UA}
        if url.startswith(API + "/rest/"):
            h.update({"LinkedIn-Version": self.version, "X-Restli-Protocol-Version": "2.0.0"})
        data = raw
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = r.read()
                return r.status, dict(r.headers), (json.loads(payload) if payload.strip().startswith(b"{") else None)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:2000]
            hint = f" {REAUTH}" if e.code == 401 else ""
            if e.code == 426 or "version" in detail.lower() and e.code == 400:
                hint += " The LinkedIn-Version may be retired: set the LINKEDIN_API_VERSION repo variable to a newer YYYYMM."
            raise SystemExit(f"LinkedIn {method} {url.split('?')[0]} failed: HTTP {e.code}: {detail}{hint}")

    def upload_image(self, owner, path):
        _, _, init = self._req("POST", f"{API}/rest/images?action=initializeUpload",
                               body={"initializeUploadRequest": {"owner": owner}})
        value = init["value"]
        with open(path, "rb") as f:
            self._req("PUT", value["uploadUrl"], raw=f.read(),
                      headers={"Content-Type": "application/octet-stream"})
        return value["image"]

    def create_post(self, payload):
        _, headers, _ = self._req("POST", f"{API}/rest/posts", body=payload)
        lower = {k.lower(): v for k, v in headers.items()}
        return lower.get("x-restli-id") or lower.get("x-linkedin-id") or ""


def check_expiry():
    raw = os.environ.get("LINKEDIN_TOKEN_EXPIRES_AT", "").strip()
    if not raw:
        return
    try:
        expires = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        print(f"::warning::LINKEDIN_TOKEN_EXPIRES_AT is not ISO 8601: {raw!r}")
        return
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires <= dt.datetime.now(dt.timezone.utc):
        sys.exit(f"The LinkedIn token expired at {raw}. {REAUTH}")


def cmd_post(args):
    pages = ll.load_pages()
    page = ll.find(pages, args.key)
    if page is None:
        sys.exit(f"No published page with key {args.key!r}.")
    state = load_state(args.state) or ll.new_state()
    prior = state["posts"].get(page.key, {})
    if prior.get("status") == "announced" and not args.again:
        print(f"{page.key} is already announced ({prior.get('urn')}); nothing to do.")
        return

    author = os.environ.get("LINKEDIN_AUTHOR_URN", "").strip()
    if args.dry_run:
        payload = ll.post_payload(page, author or "urn:li:person:DRY_RUN",
                                  "urn:li:image:DRY_RUN" if page.card else None)
        print(json.dumps(payload, indent=2))
        summary(preview(page, "LinkedIn: dry run (nothing posted)"))
        return

    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    if not token or not author.startswith("urn:li:person:"):
        sys.exit("Missing LINKEDIN_ACCESS_TOKEN secret or LINKEDIN_AUTHOR_URN variable. "
                 "Run scripts/linkedin-auth.py locally to set both.")
    check_expiry()
    if not args.no_live_check and not is_live(page.url):
        sys.exit(f"{page.url} is not live. Refusing to announce a 404.")

    li = LinkedIn(token, os.environ.get("LINKEDIN_API_VERSION", "").strip() or DEFAULT_API_VERSION)
    image = None
    if page.card:
        try:
            image = li.upload_image(author, page.card)
        except SystemExit as e:
            print(f"::warning::Card upload failed, posting without a thumbnail: {e}")
    urn = li.create_post(ll.post_payload(page, author, image))

    ll.record(state, page, now_iso(), urn)
    save_state(args.state, state)
    link = f"https://www.linkedin.com/feed/update/{urn}/" if urn else "(no post id returned)"
    summary(f"## LinkedIn: posted\n\n**{page.title}**: {link}\n")
    gh_output(urn=urn, post_url=link)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan")
    p.add_argument("--state", required=True)
    p.add_argument("--ref", default="", help="force one page: content path or section/stem")
    p.add_argument("--again", action="store_true", help="allow re-announcing a page")
    p.add_argument("--today", default="", help="override today's date (YYYY-MM-DD), for testing")
    p.add_argument("--rounds", type=int, default=int(os.environ.get("LIVE_CHECK_ROUNDS", "4")))
    p.add_argument("--wait", type=int, default=30, help="seconds between live-check rounds")
    p.add_argument("--no-live-check", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("post")
    p.add_argument("--state", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--again", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-live-check", action="store_true")
    p.set_defaults(func=cmd_post)

    args = ap.parse_args()
    args.ref = getattr(args, "ref", "").strip()
    args.func(args)


if __name__ == "__main__":
    main()
