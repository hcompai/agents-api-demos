#!/usr/bin/env python3
"""Obtain an H platform API key via the portal desktop OAuth flow (RFC 8252 + PKCE)
and write it to a .env file as H_API_KEY. Stdlib only — no dependencies.

Usage:
    python h_login.py                       # writes H_API_KEY into ./.env (skips if already set)
    python h_login.py --env-file path/.env  # target a specific .env
    python h_login.py --force               # replace an existing H_API_KEY
    python h_login.py --key-name "my-key"   # custom key name (default: "<cwd-name> @ <hostname>")
    python h_login.py --no-rotate           # keep older keys with the same name (default: revoke them)

Flow: open browser -> Google login via the portal API (portal.api.eu.hcompany.ai)
-> loopback callback -> exchange one-time code for an access token
-> create an org API key -> write .env.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

# portal API hosts (portal.hcompany.ai / platform.hcompany.ai are frontends, NOT the API)
PORTAL_API_URLS = {
    "us": "https://portal.production.hcompany.ai",
    "eu": "https://portal.api.eu.hcompany.ai",
}
# agent platform hosts, used to validate the freshly minted key end-to-end
AGP_API_URLS = {
    "us": "https://agp.hcompany.ai",
    "eu": "https://agp.eu.hcompany.ai",
}
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
    # handle_request returns after one request (or timeout); a second request can
    # arrive for /favicon.ico, so loop until we have an outcome. A monotonic
    # deadline (not a Timer thread) so nothing outlives the loop and keeps the
    # interpreter alive after a successful login.
    deadline = time.monotonic() + CALLBACK_TIMEOUT_S
    while not result and (remaining := deadline - time.monotonic()) > 0:
        server.timeout = remaining
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
    p.add_argument("--region", choices=["us", "eu"], default="eu", help="portal region (default: eu)")
    p.add_argument("--base-url", default=os.environ.get("H_PORTAL_URL"), help="override the portal API URL")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--key-name", default=None)
    p.add_argument("--force", action="store_true", help="replace an existing H_API_KEY")
    p.add_argument("--no-rotate", action="store_true", help="keep older keys with the same name")
    args = p.parse_args()
    base_url = args.base_url or PORTAL_API_URLS[args.region]

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
    authorize_url = f"{base_url}/api/auth/authorize?" + urllib.parse.urlencode(
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
        base_url,
        "POST",
        "/api/auth/desktop/exchange",
        body={"code": code, "code_verifier": verifier, "redirect_uri": redirect_uri},
    )
    access_token = tokens["access_token"]

    # 4. Resolve the organization: /auth/me, then owned orgs, then first membership
    me = api(base_url, "GET", "/api/auth/me", token=access_token)
    org_id = (me or {}).get("org_id")
    if not org_id:
        owned = api(base_url, "GET", "/api/organizations/owned", token=access_token)
        orgs = owned or api(base_url, "GET", "/api/organizations/", token=access_token)
        if not orgs:
            sys.exit("error: this account belongs to no organization — create one in the portal first")
        org_id = orgs[0]["id"]
        print(f"Using organization: {orgs[0].get('name', org_id)}")

    # 5. Rotate: revoke previous keys created under the same name
    if not args.no_rotate:
        existing = api(base_url, "GET", f"/api/organizations/{org_id}/keys/", token=access_token)
        for k in existing or []:
            if k["name"] == key_name:
                api(base_url, "DELETE", f"/api/organizations/{org_id}/keys/{k['id']}", token=access_token)
                print(f"Revoked previous key {k.get('key_display', k['id'])} ({key_name})")

    # 6. Create the key — the full value is only ever returned here
    created = api(base_url, "POST", f"/api/organizations/{org_id}/keys/", token=access_token, body={"name": key_name})

    # 7. Validate end-to-end against the agent platform before declaring victory
    agp = AGP_API_URLS[args.region]
    try:
        api(agp, "GET", "/api/v2/agents?page=1&size=1", token=created["key"])
        validated = "validated against AgP"
    except SystemExit:
        validated = "WARNING: key not (yet) accepted by AgP — it may take a moment to propagate"

    write_env(args.env_file, created["key"])
    print(f"✓ H_API_KEY written to {args.env_file} (key '{key_name}', org {org_id}, {validated})")


if __name__ == "__main__":
    main()
