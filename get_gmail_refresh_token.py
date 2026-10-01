"""ONE-TIME local helper. Prints the GMAIL_REFRESH_TOKEN to paste into a secret.

Run this on your own PC, never in Actions: it opens a browser, you sign in as
the mailbox owner, and Google hands back a token that is then good for months
without another sign-in. That is the whole point of a refresh token — the
workflow never sees a password and never shows a login screen.

BEFORE RUNNING, in Google Cloud Console (console.cloud.google.com):

  1. Create a project, or reuse one.
  2. APIs & Services -> Library -> enable **Gmail API**.
  3. APIs & Services -> OAuth consent screen -> External. Fill the app name
     and your own email. Under **Audience**, add your Gmail address as a
     **Test user**. Do not publish or submit for verification — an app in
     testing works indefinitely for its own test users.
  4. Credentials -> Create credentials -> **OAuth client ID** ->
     Application type **Desktop app**. Copy the client id and client secret.

THEN — easiest, using the JSON the console gives you on step 4:

    python get_gmail_refresh_token.py "C:/path/to/client_secret_....json"

Or without the file:

    set GMAIL_CLIENT_ID=...apps.googleusercontent.com
    set GMAIL_CLIENT_SECRET=...
    python get_gmail_refresh_token.py

(PowerShell uses $env:GMAIL_CLIENT_ID = "..." instead.)

That downloaded JSON holds the client secret. Keep it out of the repo — it is
gitignored here — and do not paste its contents anywhere.

The scope is gmail.readonly and nothing else. This reads verification mail; it
can never send, delete or modify anything in that mailbox, which is the level
of access a citation queue should have and no more.

The token it prints is a live credential. Paste it straight into
Settings -> Secrets and variables -> Actions -> New repository secret. Do not
put it in a file, a commit, a workflow input, a screenshot, or a chat window.
"""
import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
PORT = 8765
# "localhost", not "127.0.0.1": a Desktop client registers its loopback
# redirect as http://localhost, and Google matches the host literally even
# though it lets the port be anything.
REDIRECT = f"http://localhost:{PORT}/"

_result = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        # A browser asks for /favicon.ico on its own. The first version served
        # exactly one request, so whichever arrived first won — and when it was
        # the favicon, the real callback was never read and the run timed out
        # with the code sitting unclaimed in the browser.
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            return
        q = urllib.parse.parse_qs(parsed.query)
        _result.update({k: v[0] for k, v in q.items()})
        ok = "code" in _result and _result.get("state") == _result.get("_expect")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<h2>Done - close this tab and go back to the terminal.</h2>"
            if ok else
            b"<h2>Something went wrong. Check the terminal.</h2>")

    def log_message(self, *a):
        pass          # the URL carries the auth code; keep it out of the console


def from_json(path):
    """Read the client id and secret out of the console's download.

    This is the file offered on the Credentials page right after the OAuth
    client is created. A Desktop client puts them under "installed"; "web" is
    accepted too, so a wrong client type fails at Google with a clear message
    rather than here with a confusing one.
    """
    import json
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit(f"No such file: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON ({e}).")
    block = data.get("installed") or data.get("web") or data
    cid, csec = block.get("client_id", ""), block.get("client_secret", "")
    if not cid or not csec:
        sys.exit(f"{path} carries no client_id/client_secret. Is it the OAuth "
                 f"client JSON from Credentials, and not something else?")
    return cid.strip(), csec.strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        cid, csec = from_json(args[0])
        print(f"client id read from {args[0]}")
    else:
        cid = os.environ.get("GMAIL_CLIENT_ID", "").strip()
        csec = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    if not cid or not csec:
        sys.exit('Give the client-secret JSON as an argument:\n'
                 '  python get_gmail_refresh_token.py "C:/path/client_secret_....json"\n'
                 'or set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET.\n'
                 'See the header of this file for where they come from.')

    # Ties the redirect back to this run: without it, anything that reaches the
    # local port could hand us a code from somewhere else.
    state = secrets.token_urlsafe(24)
    _result["_expect"] = state

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # without this there is no refresh token
        "prompt": "consent",          # forces one even if you have approved before
        "state": state,
    })

    try:
        server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        sys.exit(f"Could not listen on {REDIRECT} ({e}). Something else is "
                 f"holding port {PORT}; close it and run this again.")
    # serve_forever, not handle_request: keep answering until the callback
    # actually arrives, however many favicon or preflight requests come first.
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("\nA browser window is opening. Sign in as the mailbox owner and approve.")
    print("If it does not open, paste this into a browser:\n")
    print(auth_url + "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Fifteen minutes, not five. The first pass through this flow includes
    # adding yourself as a Test user and reading two warning screens, and
    # timing out halfway through means starting the whole thing again.
    print(f"Waiting for the redirect on {REDIRECT} ...")
    print("(up to 15 minutes — take your time on the consent screens)")
    for tick in range(1800):
        if "code" in _result or "error" in _result:
            break
        if tick and tick % 240 == 0:
            print(f"  still waiting... {tick // 120} minute(s)")
        threading.Event().wait(0.5)
    server.shutdown()

    if _result.get("error"):
        sys.exit("Google returned: " + _result["error"]
                 + ("\n\nadmin_policy_enforced or access_denied usually means the "
                    "signed-in account is not on the Test users list."
                    if "denied" in _result["error"] else ""))
    if "code" not in _result:
        sys.exit("Timed out waiting for the redirect.\n"
                 "If you did finish the consent screens, the browser may have "
                 "been sent to a DIFFERENT run of this script — close every "
                 "leftover tab from an earlier attempt and run it once more.")
    if _result.get("state") != state:
        sys.exit("State did not match — refusing this response.")

    body = urllib.parse.urlencode({
        "code": _result["code"],
        "client_id": cid,
        "client_secret": csec,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    try:
        import json
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.load(r)
    except Exception as e:
        detail = ""
        if hasattr(e, "read"):
            detail = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"Token exchange failed: {e}\n{detail}")

    refresh = tok.get("refresh_token")
    if not refresh:
        sys.exit("Google did not return a refresh_token. That happens when the "
                 "account has already approved this client and prompt=consent "
                 "was not honoured — revoke it at "
                 "https://myaccount.google.com/permissions and run this again.")

    print("\n" + "=" * 70)
    print("GMAIL_REFRESH_TOKEN")
    print("=" * 70)
    print(refresh)
    print("=" * 70)
    print("\nPaste that straight into GitHub:")
    print("  Settings -> Secrets and variables -> Actions -> New repository secret")
    print("\nAlso add these two as secrets there:")
    print(f"  GMAIL_CLIENT_ID      {cid}")
    print("  GMAIL_CLIENT_SECRET  (from the same JSON — not printed here)")
    print("\nThis value is a live credential. It is not written to any file here,")
    print("and it must not go into a commit, a workflow input, a screenshot or a")
    print("chat window. If it is ever shown to anyone, revoke it at")
    print("https://myaccount.google.com/permissions and run this again.")
    print("\nThen: Actions -> Check Gmail connection -> Run workflow.")


if __name__ == "__main__":
    main()
