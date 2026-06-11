# hai-agents — the published Python SDK

One-line summary: how to use the `hai-agents` PyPI package (Fern-generated `Client`/`AsyncClient` + handwritten `run_session`/`SessionHandle` polling layer) instead of hand-rolling v2 HTTP — accurate as of v0.1.6, Python ≥ 3.10.

## Table of contents

1. [Install & auth](#1-install--auth)
2. [High-level helpers: run, start, steer](#2-high-level-helpers-run-start-steer)
3. [Lower-level Client surface → v2 routes](#3-lower-level-client-surface--v2-routes)
4. [Events & how polling works under the hood](#4-events--how-polling-works-under-the-hood)
5. [Errors & exceptions](#5-errors--exceptions)
6. [Gotchas](#6-gotchas)
7. [After launch: hand over the replay link](#7-after-launch-hand-over-the-replay-link)

---

## 1. Install & auth

```bash
pip install hai-agents            # SDK only
pip install "hai-agents[cli]"     # + the `hai` CLI (hai login / run / sessions ...)
export H_API_KEY=hk-...           # Client() picks this up automatically
```

```python
from hai_agents import Client, AsyncClient, HaiAgentsEnvironment

client = Client()                                   # api_key defaults to os.getenv("H_API_KEY")
client = Client(api_key="hk-...")                   # explicit key (str or zero-arg callable)
client = Client(environment=HaiAgentsEnvironment.US)  # enum: EU (default!) / US
client = Client(base_url="https://agp.staging.sandboxh.ai")  # overrides environment
```

- `HaiAgentsEnvironment.EU = "https://agp.eu.hcompany.ai"` is the **default**; `HaiAgentsEnvironment.US = "https://agp.hcompany.ai"`. Make sure the key's region matches the environment or you'll get 401s.
- No key at all → constructor raises `ApiError("The client must be instantiated be either passing in api_key or setting H_API_KEY")`.
- Other ctor kwargs: `headers`, `timeout` (default 60 s), `max_retries` (default 2), `follow_redirects`, `httpx_client`, `logging`. `AsyncClient` adds `async_token`.
- No key yet? Don't make the user copy-paste — run `scripts/h_login.py` at the skill root (see [../agp/conventions-and-sdk.md](../agp/conventions-and-sdk.md)).

## 2. High-level helpers: run, start, steer

Three layers of sugar, all in `hai_agents` (handwritten `polling.py`, not Fern-generated):

- **Blocking one-shot**: `run_session(client, **params)` / module-level twin of `client.run_session(**params)` — create + poll to terminal status, returns `SessionRunResult`.
- **Fire-and-steer**: `client.start_session(**params)` → `SessionHandle` (create, don't wait). `client.session(id)` wraps an existing id.
- **Resume polling**: `wait_for_session(client, id, from_index=0, ...)` for a session created elsewhere.
- Async mirrors: `async_run_session`, `async_wait_for_session`, `AsyncClient.run_session/start_session/session`, `AsyncSessionHandle` (same methods, `await`ed).

Create params (`CreateSessionParams`, forwarded to `sessions.create_session`): `agent` (required — agent name string **or** inline `Agent` dict), `messages` (str | message dict | list), `max_steps`, `max_time_s`, `idle_timeout_s`, `group_id`, `parent_session_id`, `overrides`, `idempotency_key`. Polling knobs on `run_session`/`wait_for_session`: `wait_for_seconds=20`, `include_events=True`, `timeout_seconds=None`, `poll_backoff_seconds=0.0`, `max_polls=None`.

### Example 1 — run a stored agent, blocking

```python
from hai_agents import Client, run_session

client = Client()  # H_API_KEY from env, EU region
result = run_session(
    client,
    agent="h/web-surfer-holo3-1-35b",   # built-in web agent, ships its own browser
    messages="What are the top 3 stories on Hacker News right now?",
)
print(result.status)   # "completed"
print(result.answer)   # str | dict (dict when the agent has an answer_format)
```

### Example 2 — inline agent spec with a web environment

```python
session = client.sessions.create_session(
    agent={
        "name": "weather-checker",
        "description": "Looks up weather on the open web",
        "instructions": "Use the search box on the page you land on. Answer in one sentence.",
        "environments": [{"id": "browser", "kind": "web", "start_url": "https://www.bing.com/"}],
        # optional: "model", "skills", "subagents", "answer_format" (JSON Schema)
    },
    messages=[{"type": "user_message", "message": "Current temperature in Paris, in Celsius?"}],
    max_steps=25, max_time_s=360.0,
)
from hai_agents import wait_for_session
result = wait_for_session(client, session.id, timeout_seconds=420)
```

(Equivalently pass the same kwargs straight to `client.run_session(...)` — it size-checks, creates, and polls in one call.)

### Example 3 — start, watch, steer mid-run

```python
handle = client.start_session(
    agent="my-org-agent",
    messages="Start researching X",
    idle_timeout_s=120,            # keep the session open for follow-ups after each answer
)
print(handle.id)

handle.status()                    # SessionStatus: .status/.error/.steps/.usage_per_model/.subagent_session_ids
handle.changes(from_index=0, wait_for_seconds=20)   # Optional[TrajectoryChanges] (None = no news)
handle.send_message({"type": "user_message", "message": "also check Y"})  # POST /messages
handle.pause(); handle.resume()
handle.force_answer()              # make it answer now
result = handle.wait_for_completion(timeout_seconds=600)   # same kwargs as wait_for_session
handle.cancel()                    # or kill it
handle.get()                       # full Session: .request/.status/.latest_answer/.created_at...
```

Async is identical with `await`:

```python
from hai_agents import AsyncClient
client = AsyncClient()
result = await client.run_session(agent="h/web-surfer-holo3-1-35b", messages="...")
handle = await client.start_session(agent="...", messages="...")  # AsyncSessionHandle
await handle.send_message({"type": "user_message", "message": "..."})
```

`SessionRunResult` (frozen dataclass): `id`, `status` (`TrajectoryStatus`), `events: list[TrajectoryEvent]`, `next_from_index` (cursor to resume polling), `final_changes: Optional[TrajectoryChanges]`, and the `.answer` property (`final_changes.answer`, `str | dict | None`).

## 3. Lower-level Client surface → v2 routes

Resource namespaces are lazy properties: `client.sessions`, `client.agents`, `client.skills`, `client.environments`, `client.vaults`. Every method takes a trailing `request_options: RequestOptions` (per-call timeout/retries/headers); `client.<ns>.with_raw_response` returns `HttpResponse[...]` wrappers with headers/status.

| SDK method | HTTP route |
|---|---|
| `sessions.create_session(agent=..., messages=..., idempotency_key=...)` | `POST /api/v2/sessions` (key sent as `Idempotency-Key` header) |
| `sessions.list_sessions(owner=, status=, agent=, group_id=, search=, created_before/after=, page=, size=, sort=)` | `GET /api/v2/sessions` → `PageSessionSummary` |
| `sessions.get_session(id)` / `get_session_status(id)` | `GET /api/v2/sessions/{id}` / `.../status` |
| `sessions.get_session_changes(id, from_index=, limit=, include_events=, wait_for_seconds=)` | `GET .../changes` (long-poll) → `Optional[TrajectoryChanges]` |
| `sessions.list_session_events(id, page=, size=, sort=)` | `GET .../events` → `PageTrajectoryEvent` |
| `sessions.send_session_messages(id, request=...)` | `POST .../messages` (single `{"type": "user_message", "message": ...}` or `{"messages": [...]}` batch; typed variants `SendSessionMessagesRequestBody_UserMessage/_Batch` in `hai_agents.sessions`) |
| `sessions.pause_session / resume_session / cancel_session / force_session_answer` | `POST .../pause` / `.../resume`, `DELETE /{id}`, `POST .../force_answer` |
| `sessions.share_session(id)` / `unshare_session(id)` | `PUT` / `DELETE .../share` → `ShareLink` |
| `sessions.submit_session_feedback(id, ...)` / `submit_event_feedback(id, event_index, ...)` | `POST .../feedback` / `.../events/{i}/feedback` |
| `sessions.get_session_quota()` | `GET /api/v2/sessions/quota` → `QuotaStatus` |
| `sessions.get_session_resource(id, bucket, key)` | `GET .../resources/{bucket}/{key}` |
| `agents.list_agents(agent_name=, search=, page=, size=, sort=)` / `create_agent` / `get_agent(agent_name)` / `update_agent` / `delete_agent` | `/api/v2/agents[/{name}]` → `PageAgent`, `Agent` |
| `skills.list_skills / create_skill / get_skill(name) / update_skill / delete_skill` | `/api/v2/skills[/{name}]` |
| `environments.list_environments / create_environment / get_environment(id) / update_environment / delete_environment` | `/api/v2/environments[/{id}]` |
| `vaults.list_vaults / create_vault / get_vault / update_vault / delete_vault / rotate_vault_token / vault_health` | `/api/v2/vaults...` |

**Pagination**: list endpoints take 1-based `page` + `size` and return plain page models (`PageAgent`, `PageSessionSummary`, `PageSkill`, ...) with `.items`, `.total`, `.page` — no auto-iterating pager; loop and bump `page` yourself.

**5 MB request guard**: the server rejects bodies over 5 MB. `run_session`/`start_session` pre-check with `assert_request_under_limit(payload)` (`MAX_REQUEST_BYTES = 5 * 1024 * 1024`) and raise `ValueError("Request payload is X MB, over the 5.00MB limit. Downscale images before sending.")`. Calling `sessions.create_session` directly skips this check — reuse the helper if you attach base64 images to `messages`.

## 4. Events & how polling works under the hood

`TrajectoryEvent` is a deliberately loose pydantic model: `type: str`, `data: Any`, `timestamp: datetime`. Common `type` values: `AgentStartedEvent`, `AgentCompletionEvent`, `AgentErrorEvent`, `AgentEvent` (generic wrapper — its `data` carries policy_event / tool_result / observation_event payloads), `LiveViewUrlEvent`, `ChatMessageEvent`. Switch on `event.type` and dig into `event.data`.

`TrajectoryChanges` (the `/changes` payload): `status`, `started_at`, `finished_at`, `error`, `new_events: Optional[list[TrajectoryEvent]]`, `answer: str | dict | None`, `metrics`.

What `wait_for_session` does for you (so don't reimplement it):

- **204 handling**: an empty long-poll window returns HTTP 204; the SDK maps that to `None` from `get_session_changes` and just re-polls — never treat it as an error.
- **Cursor**: it advances `from_index += len(changes.new_events)` and exposes the final cursor as `result.next_from_index` (pass it back as `from_index=` to resume without duplicates — never reset to 0 mid-stream).
- **Terminal detection**: status is read from `/status` (authoritative), not `/changes` — `/changes` 204s even after the session finished. Terminal = `TERMINAL_SESSION_STATUSES = {"completed", "failed", "timed_out", "interrupted"}`; test with `is_terminal_session_status(status)`.
- **Final answer**: if the streamed changes never surfaced an answer, it does one extra `get_session_changes(from_index=0, include_events=False, wait_for_seconds=0)` to fetch it.
- Pacing: the server-side long poll (`wait_for_seconds`, default 20, server cap 60) paces the loop; add `poll_backoff_seconds` only to throttle further. `include_events=False` skips `/changes` entirely and just watches `/status`.

## 5. Errors & exceptions

| Exception | Import | When |
|---|---|---|
| `ApiError` (base, has `.status_code`, `.body`, `.headers`) | `hai_agents.core.api_error` | Any non-2xx not specially typed — 401 invalid/missing `hk-` key, 403 writes to reserved `h/` resources, 404, 409 in-flight idempotent create. Also raised at construction when no api_key/H_API_KEY. |
| `UnprocessableEntityError(ApiError)` | `hai_agents` (or `hai_agents.errors`) | HTTP 422 — validation failures, blank `Idempotency-Key`, idempotency-key reuse with a different body. `.body` is an `HttpValidationError` (`.detail` list of `ValidationError`). |
| `ParsingError` | `hai_agents.core.parse_error` | 2xx body didn't match the expected model. |
| `TimeoutError` (builtin) | — | `wait_for_session`/`run_session` hit `timeout_seconds` or `max_polls` before a terminal status. The session is still running — `cancel` it or resume with `wait_for_session(client, id, from_index=...)`. |
| `ValueError` | — | Request body over the 5 MB guard (see above). |
| `httpx` transport errors | — | Network failures; the client retries failed requests up to `max_retries` (default 2) first. |

## 6. Gotchas

- **EU is the default region** (`HaiAgentsEnvironment.EU` → `agp.eu.hcompany.ai`). A US key against the default client = 401. Pass `environment=HaiAgentsEnvironment.US` or `base_url=` explicitly.
- `api_key` defaults to `os.getenv("H_API_KEY")` **evaluated at import time** of the client class defaults — set the env var before constructing. The CLI additionally reads `HAI_API_KEY`, `.env`, and `~/.config/hai/.env`, but the SDK `Client` itself only falls back to `H_API_KEY`.
- `"idle"` is **not** a terminal status for the polling helpers. If you set `idle_timeout_s`, the session sits in `idle` after answering (waiting for follow-ups) and `run_session` keeps blocking until the idle window lapses (`timed_out`/`completed`). For interactive flows use `start_session` + `handle.changes()` and check `is_terminal_session_status` / `"idle"` yourself.
- `get_session_changes` returns `Optional[TrajectoryChanges]` — `None` means "no news" (204), not failure.
- `messages` accepts a plain string; dict messages need `"type": "user_message"`. Images go in `images` as base64 data URIs (mind the 5 MB guard).
- The package imports lazily (PEP 562) — `from hai_agents import X` works for everything in `__all__`, but attribute typos surface at first access, not import.
- Pin awareness: this documents **v0.1.6**; the surface is Fern-generated from `/share/openapi.json`, so method names track the v2 API ([../agp/sessions.md](../agp/sessions.md) for route semantics).

## 7. After launch: hand over the replay link

Whenever you create a session for the user, give them the browser replay link so they can watch what the agent did:

```
https://platform.eu.hcompany.ai/agent-view/{session_id}   # EU (SDK default region)
https://platform.hcompany.ai/agent-view/{session_id}      # US
```

E.g. `print(f"Watch the run: https://platform.eu.hcompany.ai/agent-view/{handle.id}")`. Deep-linking to a specific event, sharing outside the org (`sessions.share_session`), and the rest of the agent-view UI are covered in [../extras/agent-view-replay.md](../extras/agent-view-replay.md).
