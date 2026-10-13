#!/usr/bin/env python3
"""Issue a LinkedIn access token for the announce workflow and store it in GitHub.

    python3 scripts/linkedin-auth.py            # sign in, then save to GitHub via `gh`
    python3 scripts/linkedin-auth.py --print    # sign in, print values instead of saving

Run it on your own machine: it opens LinkedIn's consent page in your browser
and catches the redirect on http://localhost:8765/callback.

Needs your LinkedIn app's credentials, from the environment or a local .env
(gitignored), or it asks for them:

    LINKEDIN_CLIENT_ID=...
    LINKEDIN_CLIENT_SECRET=...

The app needs the "Share on LinkedIn" and "Sign In with LinkedIn using OpenID
Connect" products, and http://localhost:8765/callback as an authorized
redirect URL. Self-serve tokens last 60 days with no refresh token, so you run
this again when the token-expiry issue opens. Saving with `gh` writes:

    secret   LINKEDIN_ACCESS_TOKEN       (in the `linkedin` environment)
    variable LINKEDIN_AUTHOR_URN         (urn:li:person:...)
    variable LINKEDIN_TOKEN_EXPIRES_AT   (ISO 8601, read by the expiry check)

Standard library only. The token never touches disk or the terminal unless
you pass --print.
"""
import argparse, datetime as dt, getpass, http.server, json, os, secrets, shutil
import subprocess, sys, urllib.error, urllib.parse, urllib.request, webbrowser

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPES = "openid profile w_member_social"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
ENVIRONMENT = "linkedin"


def dotenv(path=".env"):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def catch_code(expected_state):
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != "/callback":
                self.send_error(404)
                return
            q = dict(urllib.parse.parse_qsl(url.query))
            result.update(q)
            ok = q.get("state") == expected_state and "code" in q
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("Signed in. You can close this tab." if ok else
                              f"Sign-in failed: {q.get('error_description') or q.get('error') or 'state mismatch'}").encode())

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("localhost", PORT), Handler)
    while "code" not in result and "error" not in result:
        server.handle_request()
    server.server_close()
    if result.get("state") != expected_state:
        sys.exit("OAuth state mismatch; aborting.")
    if "error" in result:
        sys.exit(f"LinkedIn returned an error: {result.get('error_description') or result['error']}")
    return result["code"]


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Token exchange failed: HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")


def userinfo(token):
    req = urllib.request.Request(USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def gh(*args, stdin=None):
    return subprocess.run(["gh", *args], input=stdin, text=True, capture_output=True)


def save_to_github(repo, token, urn, expires_at):
    if gh("api", f"repos/{repo}/environments/{ENVIRONMENT}").returncode != 0:
        print(f"Creating the `{ENVIRONMENT}` environment on {repo} "
              "(add yourself as a required reviewer in Settings > Environments).")
        r = gh("api", "-X", "PUT", f"repos/{repo}/environments/{ENVIRONMENT}")
        if r.returncode != 0:
            sys.exit(f"Could not create the environment: {r.stderr.strip()}")
    steps = [
        (["secret", "set", "LINKEDIN_ACCESS_TOKEN", "--env", ENVIRONMENT, "--repo", repo], token),
        (["variable", "set", "LINKEDIN_AUTHOR_URN", "--body", urn, "--repo", repo], None),
        (["variable", "set", "LINKEDIN_TOKEN_EXPIRES_AT", "--body", expires_at, "--repo", repo], None),
    ]
    for args, stdin in steps:
        r = gh(*args, stdin=stdin)
        if r.returncode != 0:
            sys.exit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()}")
    print(f"Saved to {repo}: secret LINKEDIN_ACCESS_TOKEN (env `{ENVIRONMENT}`), "
          "variables LINKEDIN_AUTHOR_URN and LINKEDIN_TOKEN_EXPIRES_AT.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default="radra23/scryops-site")
    ap.add_argument("--print", action="store_true", help="print the values instead of saving them with gh")
    args = ap.parse_args()

    dotenv()
    client_id = os.environ.get("LINKEDIN_CLIENT_ID") or input("LinkedIn client ID: ").strip()
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET") or getpass.getpass("LinkedIn client secret: ").strip()
    if not args.print and not shutil.which("gh"):
        sys.exit("The GitHub CLI (gh) is not installed. Install it, or rerun with --print and set the values by hand.")

    state = secrets.token_urlsafe(24)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "state": state, "scope": SCOPES,
    })
    print(f"Opening LinkedIn sign-in. If no browser opens, visit:\n  {url}\n")
    webbrowser.open(url)
    code = catch_code(state)

    tok = post_form(TOKEN_URL, {
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "client_secret": client_secret,
    })
    token = tok["access_token"]
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(tok.get("expires_in", 0))))
    expires_at = expires_at.replace(microsecond=0).isoformat()
    me = userinfo(token)
    urn = f"urn:li:person:{me['sub']}"
    print(f"Signed in as {me.get('name', urn)}; token expires {expires_at}.")

    if args.print:
        print(f"\nLINKEDIN_ACCESS_TOKEN={token}\nLINKEDIN_AUTHOR_URN={urn}\nLINKEDIN_TOKEN_EXPIRES_AT={expires_at}")
    else:
        save_to_github(args.repo, token, urn, expires_at)


if __name__ == "__main__":
    main()
