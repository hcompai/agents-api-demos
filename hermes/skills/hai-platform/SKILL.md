---
name: hai-agents
description: >
  Expert knowledge of the two H Company backends: the portal (auth, organizations, API keys,
  invitations, billing at portal.api.eu.hcompany.ai / portal.production.hcompany.ai) and the
  agent platform v2 API (sessions, agents, skills, environments, vaults, long-polling, the
  hai-agents SDK at agp.hcompany.ai). Use this skill whenever the user mentions portal,
  agent_platform, platform.hcompany.ai, agp.hcompany.ai, HAI_API_KEY or hk-... keys, hai-agents
  / hai_agents, run_session, agent sessions or trajectories, agent-view or replaying a run,
  /api/v2 endpoints, browser agent environments, vaults for agent secrets, organizations or
  invitations on the H platform, the desktop OAuth/PKCE login flow, or wants to call, integrate
  with, debug, or automate anything against an H Company API, even without naming it (e.g. "get
  me an API key", "set up my .env", "launch a web agent", "why is my session stuck", "show me
  what the agent did", "why am I getting 401 from the platform?").
version: 1.0.0
metadata:
  hermes:
    tags: [h-company, platform, api, auth, agent-platform]
    category: platform
---

# H Company APIs (portal + agent platform)

> Reference docs (`references/`) and the login script (`scripts/`) are relative symlinks into the
> canonical `skills/hai-agents/`, so they're single-sourced (no duplication) yet the
> `references/...` links below resolve in-repo. `cp -RL` at install (bottom of this file) copies
> the real files.

H Company runs two backends that work together. Pick the right one first:

| You're touching | Product | Base URL | Read |
|---|---|---|---|
| Login, users, organizations, invitations, API key management, billing, STT tokens | **Portal** | EU: `https://portal.api.eu.hcompany.ai/api` · US: `https://portal.production.hcompany.ai/api` | [references/portal/](references/portal/) |
| Running agents: sessions, stored agents, skills, environments, vaults, events/long-polling, hai-agents SDK, MCP server | **Agent platform** (agp) | EU (default): `https://agp.eu.hcompany.ai/api` · US: `https://agp.hcompany.ai/api` | [references/agp/](references/agp/) |

Note: `https://platform.hcompany.ai` is the product frontend (the API-keys UI lives at
`/settings/api-keys`), not the portal API. Its `/api/*` paths return the HTML app shell, except
a server-side `/api/portal/[...path]` proxy.

They connect through one object: the H API key (`hk-...`) is created on the portal (by a
logged-in user) and consumed by the agent platform (as `Authorization: Bearer hk-...` at the
gateway). "Get a key" → portal; "use a key" → agp.

## Auth: the three mechanisms

1. **Portal session JWT.** For acting as a user on the portal (manage orgs, keys, billing). The guard is hybrid: env-prefixed `access_token` cookie first, `Authorization: Bearer <jwt>` fallback. Access tokens live 10 minutes.
2. **H API key (`hk-...`).** Machine auth for the agent platform (and the portal's `POST /api/stt/token` and `GET /api/api-keys/me`). API keys can NOT call the portal's management endpoints. On agp, the gateway validates the key and injects `X-User-*` identity headers; clients never set those.
3. **Desktop OAuth (RFC 8252 + PKCE).** How a CLI gets a portal session without a browser cookie: `GET /api/auth/authorize` (loopback `127.0.0.1` redirect + S256 challenge) → one-time `code` (60 s) → `POST /api/auth/desktop/exchange` → `{access_token, refresh_token, session_id}`.

Critical constraint: the full `hk-...` value is returned only once, at creation
(`POST /api/organizations/{org_id}/keys/`, SHA256-hashed in storage). To "retrieve" a key,
create a new one and revoke the old by name.

## Getting an HAI_API_KEY into .env automatically

Don't make the user copy-paste from the settings page
(`https://platform.hcompany.ai/settings/api-keys`). Run the bundled script (stdlib only). In
Hermes, run it from this skill's directory (after install, `~/.hermes/skills/hai/hai-agents/`):

```bash
python3 scripts/h_login.py                                          # desktop PKCE flow → writes HAI_API_KEY into ./.env, no-op if already set
python3 scripts/h_login.py --env-file /path/to/agent-sdk-demo/.env  # write where the demo MCP servers read the key
python3 scripts/h_login.py --force                                  # rotate/replace; also --region us|eu (default eu), --key-name, --no-rotate
```

It opens the browser (one Google click), exchanges the code, picks the org, revokes stale
same-name keys, creates a fresh key, and writes `.env` (chmod 600). `--region eu` (default)
targets `portal.api.eu.hcompany.ai`; `--region us` targets `portal.production.hcompany.ai`.
Headless fallback: `POST /api/auth/token` with `{email, password}` plus header
`X-SDK-Auth: true` (tokens in the body); see [references/portal/auth.md](references/portal/auth.md).

## Reference map

Portal (`references/portal/`):
- [auth.md](references/portal/auth.md): the 18 `/api/auth` routes (login, signup, Google OAuth, desktop PKCE, refresh, sessions, MFA, `/me`).
- [organizations.md](references/portal/organizations.md): orgs, memberships, invitations (owner and invitee side), temporal worker tokens.
- [api-keys.md](references/portal/api-keys.md): key create/list/revoke, `/api/api-keys/me`, how `hk-` auth works.
- [apps-billing-stt.md](references/portal/apps-billing-stt.md): applications, Stripe credits, STT, error/health conventions, environments.

Agent platform (agp):
- For exact request/response shapes (every endpoint, param, body, status code), the swagger is the source of truth: `https://agp.hcompany.ai/share/docs` (raw spec at `/share/openapi.json`).
- [agp/api-notes.md](references/agp/api-notes.md): the behavior the swagger can't express, including session lifecycle, the `/changes` 204+ETag long-poll and cursor rule, idempotency semantics, event kinds, the reserved `h/` namespace, the `web` environment, vault/proxy gotchas, the MCP server, and gateway auth.

SDKs (`hai-agents`; prefer the SDK over hand-rolled HTTP when it fits, and check the package page for the current surface, versions, and examples):
- Python: [pypi.org/project/hai-agents](https://pypi.org/project/hai-agents/): `run_session`/`start_session` → `SessionHandle`, events/polling, exceptions (defaults to the EU endpoint; set `base_url` for US).
- TypeScript: [npmjs.com/package/hai-agents](https://www.npmjs.com/package/hai-agents): `runSession` → `SessionHandle`, error classes, ESM/CJS (same EU-default gotcha).

Extras (`references/extras/`, dev UI/UX knowledge, not endpoint docs):
- [agent-view-replay.md](references/extras/agent-view-replay.md): reviewing and replaying runs in the browser (`platform[.eu].hcompany.ai/agent-view/{id}`), deep-linking to an event, sharing a run with someone outside the org.

Official hub docs ([references/llms.txt](references/llms.txt), the index of the full public docs on hub.hcompany.ai; more complete than the distilled notes above, but without their gotchas):
- The public hub brands agp as the "Computer-Use Agent API" (URLs are `hub.hcompany.ai/computer-use-agent/...`). Same product as the agent platform / agp here, just a different name.
- Every entry has a one-line description and a live URL. Fetch the matching page (the URLs already end in `.md`) for full endpoint docs: request/response shapes and examples.
- If a hub page is unreachable or moved (these are fetched live, not bundled), fall back to the agp OpenAPI for shapes: `https://agp.hcompany.ai/share/openapi.json` (`/share/docs` for the rendered swagger); it's unauthenticated and always current.

## The canonical agent workflow (agp)

1. `POST /api/v2/sessions` with a stored agent id or an inline Agent spec (`{name, instructions, model, environments: [{kind: "web", ...}], skills}`). Pass an idempotency key; a retried create replays instead of duplicating (422 conflicting reuse, 409 in-flight).
2. Long-poll `GET /api/v2/sessions/{id}/changes?from_index=N&wait_for_seconds=30` (cap 60 s). An empty window returns 204 + `ETag: <from_index>`, not an error: keep the cursor and re-poll. Advance by `from_index += len(events)`; never reset.
3. React to events (`AgentEvent.kind` ∈ policy_event / tool_result / answer_event / observation_event / message_event / error_event, plus AgentStarted/Completion/Error, MetricsUpdate, LiveViewUrl, ChatMessage). Interact via `POST .../messages`, `pause`/`resume`, `force_answer`.
4. In Python this is just `hai_agents.run_session(...)`, in TypeScript `client.runSession(...)`; check the SDK package page ([PyPI](https://pypi.org/project/hai-agents/) / [npm](https://www.npmjs.com/package/hai-agents)) before hand-rolling HTTP.
5. Always hand the user the replay link and offer to open it: `https://platform.hcompany.ai/agent-view/{session_id}` (EU sessions → `platform.eu.hcompany.ai`; match the region of the API you called). The moment a run starts, ask the user whether to open it in their browser; on yes, run `open "<agent-view-url>"` (macOS; `xdg-open` on Linux). Watching the agent live beats reading your summary. Details: [references/extras/agent-view-replay.md](references/extras/agent-view-replay.md).

## Gotchas that bite

- **Portal trailing slashes matter**: `GET /api/organizations/` and `.../keys/`.
- **The hai-agents SDK defaults to the EU endpoint** (`agp.eu.hcompany.ai`); set `base_url` for US.
- **Portal cookie names are environment-prefixed** (`staging_access_token`, `dev_...`, `sandbox_...`); `X-SDK-Auth: true` response bodies use those prefixed names as JSON keys.
- **PKCE redirect is loopback-only**: `http://127.0.0.1:*` or `[::1]`; `localhost` is rejected by design.
- **agp's only public environment kind is `web`** (Browser); never author `Browser.session_id` (runtime-only).
- **Reserved `h/` namespace** on agp is read-only for org users; org rows shadow same-id reserved rows.
- **Vault create/rotate is not idempotent**: list before retrying a timed-out create. Vault↔session attachment is platform-managed (no public `vault_id` field on `SessionRequest`).
- **Quota**: check `GET /api/v2/sessions/quota` before mass-launching sessions.

## Something broken? Report it to feedback@hcompany.ai

If you hit what looks like a platform-side problem (an endpoint behaving differently than
documented here, an unexplained 5xx, a session stuck with no events, a key that AgP rejects
right after creation), don't leave the user stranded: write the report for them and offer to
send it to feedback@hcompany.ai.

Write the full report yourself (that's the point: the user has nothing to do): one-line summary,
region and host called, exact endpoint and method, full response (status, `detail`/`title`,
headers like `Retry-After`/`ETag`), timestamp (UTC), session/trajectory id and the agent-view
link if relevant, what was expected versus observed, and minimal reproduction steps. Never
include `hk-` keys or tokens in the report.

Then offer to open the user's default email app, pre-filled via a `mailto:` link; the user only
has to hit Send. Write the report to a temp file, then:

```bash
open "mailto:feedback@hcompany.ai?subject=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("[agp] 504 on /v2/sessions/{id}/changes"))')&body=$(python3 -c 'import urllib.parse;print(urllib.parse.quote(open("/tmp/h-feedback.txt").read()))')"
```

(`open` is macOS; use `xdg-open` on Linux. Keep the body to a few KB, since `mailto:` has length
limits, and paste everything inline with no attachments.) If a mail tool is connected (e.g. Gmail
MCP), a draft there is a fine alternative. Either way, show the user the report before anything
is sent: they press Send, not you.

## Source of truth

Shapes in doubt → start from the docs index in [references/llms.txt](references/llms.txt) and
fetch the matching live page on hub.hcompany.ai. For the exact request/response shapes, the
public agp OpenAPI is authoritative: `https://agp.hcompany.ai/share/docs`.

## Install (Hermes Agent)

`references/` and `scripts/` are symlinks into the canonical `skills/hai-agents/`. Install with
`cp -RL` (run from the repo root) so the `-L` dereferences them into a self-contained copy:

```bash
mkdir -p ~/.hermes/skills/hai
cp -RL hermes/skills/hai-agents ~/.hermes/skills/hai/hai-agents
# then restart Hermes; it re-scans ~/.hermes/skills/ on startup
```
