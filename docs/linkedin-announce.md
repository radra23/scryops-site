# Announcing new pages on LinkedIn

When a page goes live on scryops.dev, a workflow drafts a LinkedIn post for it,
waits for your approval, then posts it to your profile with the page's share
card as the preview image.

```
push to main ─► Deploy Hugo site ─► Announce on LinkedIn
                                     plan: next new page, live? preview in run summary
                                     post: ⏸ approval (env `linkedin`) ─► LinkedIn ─► ledger
```

It posts a *link post* ("New article on scryops: …"), not a native LinkedIn
Article. LinkedIn has no API for Articles.

## How "new" is decided

A ledger, `announced.json` on the `linkedin-state` branch, lists every page
already announced. A page is announced when it is published (`draft: false`),
dated today or earlier, not in the ledger, and its URL returns 200. That covers
the usual flow of flipping a draft to `false`, and makes reruns safe.

- **First run:** there is no ledger, so every page already live is recorded as
  baseline and nothing is posted. Turning this on never floods your feed.
- **One page per run**, oldest first. The daily run (07:41 UTC) drains any queue
  and catches pages that weren't live when their deploy finished.
- **Future-dated pages** wait: Hugo only builds them in a deploy after their date.

## One-time setup

1. **LinkedIn app.** At <https://www.linkedin.com/developers/apps> create an app
   (it needs a Company Page to attach to; the ScryOps page is fine), then under
   **Products** add *Share on LinkedIn* and *Sign In with LinkedIn using OpenID
   Connect*. Both are self-serve, no review. Under **Auth**, add
   `http://localhost:8765/callback` as an authorized redirect URL.
2. **Credentials.** Put the app's client ID and secret in `.env` (gitignored):
   ```
   LINKEDIN_CLIENT_ID=...
   LINKEDIN_CLIENT_SECRET=...
   ```
3. **Token.** With the GitHub CLI signed in as radra23:
   ```sh
   python3 scripts/linkedin-auth.py
   ```
   It opens LinkedIn, you approve, and it saves the secret
   `LINKEDIN_ACCESS_TOKEN` (in the `linkedin` environment) plus the variables
   `LINKEDIN_AUTHOR_URN` and `LINKEDIN_TOKEN_EXPIRES_AT`. It creates the
   environment if it's missing.
4. **Approval gate.** Settings → Environments → `linkedin` → *Required
   reviewers* → add yourself. Optionally restrict deployment branches to
   `main`. Without a reviewer, posts go out unattended.
5. **Try it.** Actions → *Announce on LinkedIn* → *Run workflow* with
   `dry_run` ticked. The first run records the baseline; run it again with a
   page path to see a real preview.

## Day to day

Publish as usual. After the deploy, the run summary shows the exact post. You
get the approval request from GitHub; approve, and the environment link opens
the post on LinkedIn.

Per-page frontmatter, both optional:

```yaml
linkedin: false            # never announce this page
linkedin_text: |           # your own post text instead of the generated one
  Most sampling advice optimises for cost and quietly loses the requests you need.

  https://scryops.dev/articles/sampling-strategy/

  #Tracing #OpenTelemetry
```

`#Words` become real LinkedIn hashtags; everything else is escaped for you.
The generated text is the section lead and title, the excerpt, the link, and up
to three hashtags from `tags`.

**Announce an older page** (for example one swallowed by the baseline): run the
workflow manually with `page` set to `content/articles/foo.md` or
`articles/foo`. Tick `again` to repost something already announced.

## Token renewal (every 60 days)

Self-serve LinkedIn tokens last 60 days and come with no refresh token, so a
human signs in again. Two weeks before expiry, *LinkedIn token expiry* opens an
issue. Run `python3 scripts/linkedin-auth.py`; the next weekly check closes the
issue. If the token does lapse, the post job fails with a re-auth message and
the page stays queued, so nothing is lost.

## Knobs and files

| What | Where |
|---|---|
| API version (`YYYYMM`, default `202608`) | repo variable `LINKEDIN_API_VERSION`; bump it when LinkedIn retires a version |
| Post text template | `plain_text()` in `scripts/linkedin_lib.py` |
| Ledger | `announced.json` on branch `linkedin-state` (edit by hand to skip or reset) |
| Workflows | `.github/workflows/linkedin.yml`, `.github/workflows/linkedin-token-check.yml` |
| Tests | `pytest scripts/test_linkedin_lib.py` |

Posting to the ScryOps **Company Page** instead of your profile needs LinkedIn's
Community Management API, which goes through review; that would be a separate
change.
