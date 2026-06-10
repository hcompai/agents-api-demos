#!/usr/bin/env python3
"""Obtain an H platform API key via the portal-h desktop OAuth flow (RFC 8252 + PKCE)
and write it to a .env file as H_API_KEY. Stdlib only — no dependencies.

Usage:
    python h_login.py                       # writes H_API_KEY into ./.env (skips if already set)
    python h_login.py --env-file path/.env  # target a specific .env
    python h_login.py --force               # replace an existing H_API_KEY
    python h_login.py --key-name "my-key"   # custom key name (default: "<cwd-name> @ <hostname>")
    python h_login.py --no-rotate           # keep older keys with the same name (default: revoke them)

Flow: open browser -> Google login on platform.hcompany.ai -> loopback callback
-> exchange one-time code for an access token -> create an org API key -> write .env.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_BASE_URL = "https://platform.hcompany.ai"
CALLBACK_TIMEOUT_S = 180

SUCCESS_HTML = b"""<!doctype html><html><head><meta charset="utf-8"><title>H Login</title></head>
<body style="font-family:system-ui;display:flex;justify-content:center;margin-top:15vh">
<div style="text-align:center"><h1>&#10003; Logged in</h1>
<p>Your H_API_KEY is being written to your .env file.<br>You can close this tab.</p></div>
</body></html>"""


def api(base_url: str, method: str, path: str, token: str | None = None, body: dict | None = None):
    req = urllib.request.Request(
        base_url + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        sys.exit(f"error: {method} {path} -> HTTP {e.code}: {detail}")


def wait_for_code(port: int) -> str:
    """Run a one-shot loopback HTTP server and return the ?code= it receives."""
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SUCCESS_HTML)
            if "code" in params:
                result["code"] = params["code"][0]
            elif "error" in params:
                result["error"] = params["error"][0]

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = CALLBACK_TIMEOUT_S
    # handle_request returns after one request (or timeout); a second request can
    # arrive for /favicon.ico, so loop until we have an outcome.
    deadline = threading.Event()
    threading.Timer(CALLBACK_TIMEOUT_S, deadline.set).start()
    while not result and not deadline.is_set():
        server.handle_request()
    server.server_close()
    if "error" in result:
        sys.exit(f"error: OAuth callback returned error={result['error']}")
    if "code" not in result:
        sys.exit(f"error: no callback received within {CALLBACK_TIMEOUT_S}s")
    return result["code"]


def write_env(env_path: str, key_value: str) -> None:
    lines: list[str] = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.read().splitlines()
    lines = [l for l in lines if not l.startswith("H_API_KEY=")]
    lines.append(f"H_API_KEY={key_value}")
    with open(env_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default=os.environ.get("H_PORTAL_URL", DEFAULT_BASE_URL))
    p.add_argument("--env-file", default=".env")
    p.add_argument("--key-name", default=None)
    p.add_argument("--force", action="store_true", help="replace an existing H_API_KEY")
    p.add_argument("--no-rotate", action="store_true", help="keep older keys with the same name")
    args = p.parse_args()

    if not args.force and os.path.exists(args.env_file):
        with open(args.env_file) as f:
            if any(l.startswith("H_API_KEY=") and l.strip() != "H_API_KEY=" for l in f):
                print(f"H_API_KEY already set in {args.env_file} — nothing to do (use --force to replace).")
                return

    key_name = args.key_name or f"{os.path.basename(os.getcwd())} @ {socket.gethostname()}"

    # 1. PKCE pair + loopback listener
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    # 2. Send the user to Google login via the portal
    authorize_url = f"{args.base_url}/api/auth/authorize?" + urllib.parse.urlencode(
        {
            "provider": "google",
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    print("Opening browser for H platform login…")
    print(f"(if nothing opens, visit: {authorize_url})")
    webbrowser.open(authorize_url)

    # 3. Receive the one-time code (valid 60 s) and exchange it (PKCE-verified)
    code = wait_for_code(port)
    tokens = api(
        args.base_url,
        "POST",
        "/api/auth/desktop/exchange",
        body={"code": code, "code_verifier": verifier, "redirect_uri": redirect_uri},
    )
    access_token = tokens["access_token"]

    # 4. Pick the organization
    orgs = api(args.base_url, "GET", "/api/organizations/", token=access_token)
    if not orgs:
        sys.exit("error: this account belongs to no organization")
    if len(orgs) == 1:
        org = orgs[0]
    else:
        for i, o in enumerate(orgs):
            print(f"  [{i}] {o['name']} ({o['id']})")
        org = orgs[int(input("Organization number: "))]

    # 5. Rotate: revoke previous keys created under the same name
    if not args.no_rotate:
        existing = api(args.base_url, "GET", f"/api/organizations/{org['id']}/keys/", token=access_token)
        for k in existing or []:
            if k["name"] == key_name:
                api(args.base_url, "DELETE", f"/api/organizations/{org['id']}/keys/{k['id']}", token=access_token)
                print(f"Revoked previous key {k.get('key_display', k['id'])} ({key_name})")

    # 6. Create the key — the full value is only ever returned here
    created = api(
        args.base_url, "POST", f"/api/organizations/{org['id']}/keys/", token=access_token, body={"name": key_name}
    )

    write_env(args.env_file, created["key"])
    print(f"✓ H_API_KEY written to {args.env_file} (key '{key_name}', org '{org['name']}')")


if __name__ == "__main__":
    main()
