#!/usr/bin/env python3
"""Obtain an H platform API key via the portal desktop OAuth flow (RFC 8252 + PKCE)
and write it to a .env file as HAI_API_KEY. Stdlib only — no dependencies.

Usage:
    python h_login.py                       # writes HAI_API_KEY into ./.env (skips if already set)
    python h_login.py --env-file path/.env  # target a specific .env
    python h_login.py --force               # replace an existing HAI_API_KEY
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

# portal API hosts
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

# Loopback callback pages — same design as `hai login` (hai_agents_cli/login_pages.py).
_CSS = """
:root {
  color-scheme: dark;
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Inter", system-ui, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  font-family: var(--font-sans);
  color: #ffffff;
  background:
    radial-gradient(120% 80% at 50% -10%, rgba(255,255,255,0.05) 0%, transparent 55%),
    radial-gradient(80% 60% at 50% 36%, #15151a 0%, #07070a 55%, #000 100%);
  background-color: #000;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  overflow: hidden;
  position: relative;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
body::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.5 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/></svg>");
  opacity: 0.035;
  mix-blend-mode: screen;
}
main {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 28px;
  animation: fade-in 600ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
}
.mark {
  width: 96px;
  height: 96px;
  filter: drop-shadow(0 12px 32px rgba(0,0,0,0.55));
  animation: mark-pop 700ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
h1 { margin: 0; font-size: 2rem; font-weight: 600; letter-spacing: -0.025em; line-height: 1.1; }
p {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.45;
  color: rgba(255,255,255,0.66);
  max-width: 360px;
  letter-spacing: -0.005em;
}
.copy { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--pill-bg);
  border: 1px solid var(--pill-border);
  color: var(--pill-fg);
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: -0.005em;
}
.pill svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  fill: none;
}
main[data-status="success"] {
  --pill-bg: rgba(76, 195, 138, 0.18);
  --pill-border: rgba(76, 195, 138, 0.40);
  --pill-fg: #7be8a8;
}
main[data-status="error"] {
  --pill-bg: rgba(229, 72, 77, 0.18);
  --pill-border: rgba(229, 72, 77, 0.40);
  --pill-fg: #ff8a8d;
}
@keyframes fade-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes mark-pop {
  from { opacity: 0; transform: scale(0.85); }
  to   { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  main, .mark { animation: none; }
}
"""

_MARK_SVG = (
    '<svg class="mark" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<path d="M512,0 C708.1,0 798.1,0 866.5,32.5 C924.4,60 964,99.6 991.5,157.5 '
    "C1024,225.9 1024,315.9 1024,512 C1024,708.1 1024,798.1 991.5,866.5 "
    "C964,924.4 924.4,964 866.5,991.5 C798.1,1024 708.1,1024 512,1024 "
    "C315.9,1024 225.9,1024 157.5,991.5 C99.6,964 60,924.4 32.5,866.5 "
    "C0,798.1 0,708.1 0,512 C0,315.9 0,225.9 32.5,157.5 "
    'C60,99.6 99.6,60 157.5,32.5 C225.9,0 315.9,0 512,0 Z" fill="#0d0d11"/>'
    '<g fill="#fafafc" transform="translate(105, 248) scale(22)">'
    '<path d="M24.6374 11.9998C24.6374 18.6272 19.1221 23.9998 12.3186 23.9998'
    "C5.5152 23.9998 -7.62939e-05 18.6272 -7.62939e-05 11.9998C-7.62939e-05 5.37234 "
    "5.5152 -0.000244141 12.3186 -0.000244141C19.1221 -0.000244141 24.6374 5.37234 "
    '24.6374 11.9998Z"/>'
    '<path d="M28.9336 7.42969H31.1255V10.9315H34.808V7.42969H36.9999V16.4831H34.808'
    'V12.8105H31.1255V16.4831H28.9336V7.42969Z"/>'
    "</g></svg>"
)

_ICON_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>'
_ICON_X = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'


def _page(*, title: str, status: str, pill: str, headline: str, subtitle: str, icon: str) -> bytes:
    return (
        "<!doctype html>"
        '<html lang="en" data-theme="dark">'
        f'<head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>hai - {title}</title>"
        f"<style>{_CSS}</style></head>"
        f'<body><main data-status="{status}">{_MARK_SVG}'
        f'<div class="copy">'
        f'<span class="pill">{pill}{icon}</span>'
        f"<h1>{headline}</h1><p>{subtitle}</p>"
        f"</div></main></body></html>"
    ).encode()


SUCCESS_HTML = _page(
    title="Signed in",
    status="success",
    pill="Signed in",
    headline="You're connected to the H Agent API.",
    subtitle="You can close this tab and return to your terminal.",
    icon=_ICON_CHECK,
)

ERROR_HTML = _page(
    title="Sign-in failed",
    status="error",
    pill="Sign-in failed",
    headline="Something went wrong",
    subtitle="Return to your terminal for details, then run h login again.",
    icon=_ICON_X,
)


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
            self.wfile.write(ERROR_HTML if "error" in params else SUCCESS_HTML)
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
    lines = [line for line in lines if not line.startswith("HAI_API_KEY=")]
    lines.append(f"HAI_API_KEY={key_value}")
    with open(env_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", choices=["us", "eu"], default="eu", help="portal region (default: eu)")
    p.add_argument("--base-url", default=os.environ.get("H_PORTAL_URL"), help="override the portal API URL")
    p.add_argument("--env-file", default=".env")
    p.add_argument("--key-name", default=None)
    p.add_argument("--force", action="store_true", help="replace an existing HAI_API_KEY")
    p.add_argument("--no-rotate", action="store_true", help="keep older keys with the same name")
    args = p.parse_args()
    base_url = args.base_url or PORTAL_API_URLS[args.region]

    if not args.force and os.path.exists(args.env_file):
        with open(args.env_file) as f:
            if any(line.startswith("HAI_API_KEY=") and line.strip() != "HAI_API_KEY=" for line in f):
                print(f"HAI_API_KEY already set in {args.env_file} — nothing to do (use --force to replace).")
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
    print(f"✓ HAI_API_KEY written to {args.env_file} (key '{key_name}', org {org_id}, {validated})")


if __name__ == "__main__":
    main()
