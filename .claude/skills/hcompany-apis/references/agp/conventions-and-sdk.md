# Agent Platform v2 — Conventions, Auth, Errors, SDKs, MCP

One-line summary: cross-cutting reference for the Agent Platform (AgP) v2 API — base URLs and environments, the H API key auth flow, error shapes, how the published `hai-agents` SDKs map to v2 HTTP calls, and the `/mcp` server.

## Table of contents

1. [Base URLs & environments](#1-base-urls--environments)
2. [Authentication end-to-end](#2-authentication-end-to-end)
3. [Error conventions](#3-error-conventions)
4. [SDK mapping (hai-agents)](#4-sdk-mapping-hai-agents)
5. [MCP server](#5-mcp-server)

---

## 1. Base URLs & environments

| Environment | API base URL | Swagger UI |
|---|---|---|
| Production (US) | `https://agp.hcompany.ai/api` | `https://agp.hcompany.ai/share/docs` |
| Production (EU) | `https://agp.eu.hcompany.ai/api` | `https://agp.eu.hcompany.ai/share/docs` |
| Staging | `https://agp.staging.sandboxh.ai/api` | `https://agp.staging.sandboxh.ai/share/docs` |
| Dev | `https://agp.dev.sandboxh.ai/api` | `https://agp.dev.sandboxh.ai/share/docs` |
| Local | `http://localhost:8000` | `http://localhost:8000/share/docs` |

The OpenAPI schema declares two SDK regions: **Europe** `https://agp.eu.hcompany.ai` (listed first, so it is the SDK default environment) and **United States** `https://agp.hcompany.ai`.

### URL surface

| Path | What |
|---|---|
| `/api/v2/...` | The v2 API: sessions, agents, skills, environments, vaults |
| `/mcp` | MCP server, streamable-HTTP. Public URL: `https://agp.hcompany.ai/mcp` (also `https://agp.eu.hcompany.ai/mcp`) |
| `/share/...` | Public share surface (e.g. `/share/api/v1/trajectories/{id}` for shared sessions) plus the docs |
| `/api` (GET) | Root discovery endpoint listing routes + `"docs": "/share/docs"` |

### OpenAPI & docs

The OpenAPI schema is served unauthenticated at `/share/openapi.json` and rendered at `/share/docs`. Generated SDKs are built from `/share/openapi.json`.

## 2. Authentication end-to-end

```
client ── Authorization: Bearer hk-... ──> API Gateway (Lambda authorizer)
            validates the key, then injects identity headers:
              X-User-Sub, X-User-Org, X-User-Role, X-User-Org-Role, X-User-Email
          ──> AgP backend (agent_api routers never see the key, only the headers)
```

- **Getting a key**: create an H API key (`hk-` prefix) in the platform — [platform.hcompany.ai](https://platform.hcompany.ai/) (docs also reference its predecessor portal at portal.hcompany.ai). No key yet? Don't send the user to copy-paste from the settings page: the portal side of this skill documents the full automated flow (desktop OAuth → key creation → `.env` write) in [../portal/api-keys.md](../portal/api-keys.md), and `scripts/h_login.py` at the skill root does it end-to-end — offer to run it. Send the key on every request:

```bash
curl https://agp.hcompany.ai/api/v2/agents \
  -H "Authorization: Bearer $H_API_KEY"
```

- **Header injection**: the gateway's Lambda authorizer validates the `hk-` key and stamps `X-User-Sub` (user UUID), `X-User-Org` (org UUID), `X-User-Role`, `X-User-Org-Role`, `X-User-Email`. These headers never appear in the OpenAPI schema, and you cannot meaningfully set them yourself through the gateway.

### Authentication outcomes

Protected routes require `X-User-Sub` **and** `X-User-Org` (i.e. a valid `hk-` key at the gateway). Missing identity → `401 {"detail": "Authentication required"}`; non-UUID values → `400 {"detail": "Invalid user or org ID"}`. Some session read routes accept **optional** auth (publicly shared sessions are readable unauthenticated — see the sessions reference). Reserved `h/`-namespaced resources are **read-only for org users**: writes to them return `403`.

## 3. Error conventions

All errors follow the FastAPI convention — a JSON body with a `detail` string:

```json
{"detail": "Authentication required"}
```

| Status | When |
|---|---|
| 400 | Malformed identity headers (non-UUID `X-User-Sub`/`X-User-Org`) |
| 401 | No/invalid identity on a protected route — `{"detail": "Authentication required"}` |
| 403 | Insufficient permissions — e.g. writing to a reserved `h/` resource (read-only for org users) |
| 404 | Resource not found (raised by service implementations) |
| 409 | Conflict (e.g. creating a skill/agent that already exists) |
| 422 | Validation errors; blank `Idempotency-Key` (`"Idempotency-Key must not be blank"`); `IdempotencyKeyConflict` |
| 503 | Upstream Redis-stream failure (non-timeout) — body `{"detail": "Upstream temporarily unavailable while <publishing|consuming> command"}`, with `Retry-After: 1` |
| 504 | Upstream Redis-stream timeout — `{"detail": "Upstream timeout while <publishing|consuming> command"}` |

Specifics worth knowing:

- `agent_api/exceptions.py` defines `IdempotencyKeyConflict` ("Same Idempotency-Key, different request body") and `KEY_MAX_LEN = 255`. The sessions router maps the conflict to **HTTP 422** on `POST /api/v2/sessions`.
- `GET /api/v2/sessions/{id}/changes` returns **204 No Content** (with an `ETag` header equal to `from_index`) when there are no new events past `from_index` — even after the session has finished. Poll `/status` for terminal state (the SDK does this for you).
- Request bodies over **5 MB** are rejected by the server; the SDKs enforce this client-side (`MAX_REQUEST_BYTES`) with a clear `ValueError` ("Downscale images before sending").
- The 503/504 mapping lives in `hplatform/app.py` (`OneShotWriteError`/`OneShotReadError` handlers) and applies to command publish/consume paths.

## 4. SDK mapping (hai-agents)

`sdk-codegen/` generates both public SDKs from the public v2 OpenAPI schema with [Fern](https://buildwithfern.com) (`fern/generators.yml`, normalized by `prepare_openapi.py`):

- **Python**: package `hai_agents`, published to PyPI as [`hai-agents`](https://pypi.org/project/hai-agents/) (mirror repo `hcompai/hai-agents-python`). Entry points: `hai_agents.Client` / `hai_agents.AsyncClient` (overlay subclasses of Fern's `BaseClient`), plus procedural helpers `run_session`, `wait_for_session`, `async_run_session`, `async_wait_for_session` and the `SessionHandle` / `AsyncSessionHandle` classes.
- **TypeScript**: npm [`hai-agents`](https://www.npmjs.com/package/hai-agents) (mirror `hcompai/hai-agents-ts`), client `HaiAgentsClient`, namespace `HaiAgents`, helpers `runSession` / `waitForSession`.

Auth: the bearer arg is renamed to `api_key` (Python) / `apiKey` (TS) with an **`H_API_KEY` env fallback**. Environments enum `HaiAgentsEnvironment` — `Eu` (default, `https://agp.eu.hcompany.ai`) and `Us` (`https://agp.hcompany.ai`). Operation IDs are FastAPI function names with the `_api_v2_...` suffix stripped, so SDK methods match route function names (`create_session`, `get_session_changes`, ...).

### Example 1 — `run_session` (create and block until done)

```python
from hai_agents import Client, HaiAgentsEnvironment

client = Client(environment=HaiAgentsEnvironment.US)  # api_key defaults to $H_API_KEY
result = client.run_session(
    agent="h/surfer",
    messages="Find the current weather in Paris",
)
print(result.status, result.answer)
```

Underlying HTTP calls:

1. `POST /api/v2/sessions` (201) — body from the flat `CreateSessionParams` (`agent`, `messages`, `overrides`, `max_steps`, `max_time_s`, `idle_timeout_s`, `idempotency_key`, ...).
2. Poll loop until terminal status (`completed`, `failed`, `timed_out`, `interrupted`):
   - `GET /api/v2/sessions/{id}/changes?from_index=N&wait_for_seconds=20&include_events=true` — long-poll; 204 means no new events; advance `from_index` by `len(new_events)`.
   - `GET /api/v2/sessions/{id}/status` — authoritative terminal check.
3. If streaming never surfaced the answer: one final `GET /api/v2/sessions/{id}/changes?from_index=0&wait_for_seconds=0&include_events=false`.

### Example 2 — `start_session` + handle methods

```python
handle = client.start_session(agent="h/surfer", messages="...")   # POST /api/v2/sessions
handle.send_message("Also check tomorrow")  # POST /api/v2/sessions/{id}/messages   (202)
handle.status()                             # GET  /api/v2/sessions/{id}/status
result = handle.wait_for_completion()       # poll loop as above
```

| SDK call | HTTP |
|---|---|
| `client.sessions.create_session(...)` | `POST /api/v2/sessions` (201; optional `Idempotency-Key`) |
| `client.sessions.get_session_changes(id, ...)` | `GET /api/v2/sessions/{id}/changes` (200 or 204) |
| `client.sessions.get_session_status(id)` | `GET /api/v2/sessions/{id}/status` |
| `handle.get()` | `GET /api/v2/sessions/{id}` |
| `handle.send_message(msg)` | `POST /api/v2/sessions/{id}/messages` (202) |
| `handle.pause()` / `handle.resume()` | `POST /api/v2/sessions/{id}/pause` / `.../resume` (202) |
| `handle.cancel()` | `DELETE /api/v2/sessions/{id}` (204) |
| `handle.force_answer()` | `POST /api/v2/sessions/{id}/force_answer` (202) |
| `client.session(id)` | no call — wraps an existing id in a `SessionHandle` |

### Example 3 — catalog resources

```python
page = client.agents.list_agents(page=1, size=20)      # GET  /api/v2/agents
skill = client.skills.create_skill(                     # POST /api/v2/skills (201)
    name="my-skill", description="Example", body="Do the thing.",
)
```

Same pattern for `client.environments` (`/api/v2/environments`). The polling/overlay layer is hand-written in `sdk-codegen/python/{polling,client}.py.static` (TS equivalents in `ts/`) and overlaid at generation time; everything else is generated.

## 5. MCP server

The Agent API MCP (`hplatform/mcp/server.py`, FastMCP, name `hai-agents`) is mounted **in-process** at `/mcp` — stateless streamable-HTTP with JSON responses, registry name `io.github.hcompai/hai-agents` (`mcp/server.json`). It is a thin proxy over `/api/v2`: tool calls are dispatched against the app itself reusing the caller's gateway-injected `X-User-*` identity, so it requires the same `Authorization: Bearer hk-...` header. Missing identity yields the tool error "Missing identity: authenticate with an 'hk-' key to inject X-User-* headers."

| Tool | Backing v2 call(s) |
|---|---|
| `run_agent(task, agent, max_steps?, max_time_s?, idempotency_key?)` | `POST /v2/sessions`, then polls up to ~24 s (`AGP_RUN_BUDGET_S`) for an answer; otherwise returns a session handle to wait on |
| `wait_for_session(session_id, wait=True)` | `/v2/sessions/{id}/changes` + `/status` long-poll, or a snapshot when `wait=False` |
| `list_agents(page, size)` | `GET /v2/agents` (org agents + public `h/` agents; returns `name`/`description`) |
| `send_message(session_id, message)` | `POST /v2/sessions/{id}/messages` |
| `cancel_session(session_id)` | `DELETE /v2/sessions/{id}` (404 treated as no-op) |
| `share_session(session_id)` | `POST /v2/sessions/{id}/share` → absolute share URL |

Endpoints: `https://agp.hcompany.ai/mcp` (US) and `https://agp.eu.hcompany.ai/mcp` (EU). Works today in IDE/programmatic MCP hosts (Cursor, VS Code, Claude Code, OpenAI API) via the bearer header; hosts that mandate OAuth (Claude.ai web, ChatGPT app) need the deferred OAuth 2.1 flow. Smoke test: `uv run --with fastmcp python mcp/smoke.py --url https://agp.eu.hcompany.ai/mcp` (reads `HAI_API_KEY`).
