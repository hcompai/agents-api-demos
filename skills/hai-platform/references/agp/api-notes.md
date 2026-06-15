# Agent Platform v2 (agp) — behavioral notes

The **swagger is the source of truth for shapes**: every endpoint, query param, request/response
body, and status code lives at `https://agp.hcompany.ai/share/docs` (raw spec, unauthenticated, at
`/share/openapi.json`). This file holds only the behavior the OpenAPI schema *can't* express — the
semantics, gotchas, and field tricks you'd otherwise learn by getting burned. When a shape is in
doubt, fetch the spec; when behavior is in doubt, read here.

## Base URLs & regions

| Region | API base | Swagger | MCP |
|---|---|---|---|
| EU (SDK default) | `https://agp.eu.hcompany.ai/api` | `…/share/docs` | `https://agp.eu.hcompany.ai/mcp` |
| US | `https://agp.hcompany.ai/api` | `…/share/docs` | `https://agp.hcompany.ai/mcp` |

The OpenAPI lists EU first, so the generated SDKs default to EU — set `base_url` for US. Staging/dev
live under `*.sandboxh.ai`. `GET /api` is a root discovery endpoint listing routes + `"docs"`.

## Auth at the gateway

Send `Authorization: Bearer hk-...` on every request. The API gateway's Lambda authorizer validates
the key and **injects** identity headers (`X-User-Sub`, `X-User-Org`, plus `X-User-Role` /
`X-User-Org-Role` / `X-User-Email`) — the backend never sees the key, only the headers, and you
cannot set those headers yourself through the gateway. Missing identity → `401`; non-UUID values →
`400 Invalid user or org ID`. Some session *read* routes accept optional auth (publicly shared
sessions are readable unauthenticated). No key yet? See [../portal/api-keys.md](../portal/api-keys.md)
and `scripts/h_login.py` — don't make the user copy-paste from the settings page.

## Sessions — running an agent

**Lifecycle**: `pending` (provisioning, async) → `running`/`idle` → terminal (`completed`,
`failed`, `timed_out`, `interrupted`). `POST /api/v2/sessions` returns `201` immediately with status
`pending`; the agent starts later. Messages sent while `pending` are buffered until it starts.
Sending a message to a *terminal* session restarts it; to a *paused* one auto-resumes it.

**Long-poll `GET /{id}/changes?from_index=N&wait_for_seconds=S`** — this is the heart of watching a run:
- `204` (empty body, header `ETag: <from_index>`) means **no new events within the wait window — this
  is the normal "keep polling" signal, not an error.** Keep your cursor and re-poll.
- **Cursor rule**: next `from_index` = previous `from_index` + `len(new_events)`. The cursor is an
  event *count*, never an event id. Don't reset it.
- `wait_for_seconds` is capped server-side at **60** (`> 60 → 422`). `0` = no wait, return immediately.
- `include_events=false` still gates 200-vs-204 on event arrival but returns `new_events: []`.
- Stop when `status` is terminal **and** you've drained `new_events`. For chat-style use, treat
  `idle` + a fresh `answer` as "the turn is done". Force a wrap-up with `POST /{id}/force_answer`.
- `error` in the body is only populated for H-employee callers; otherwise always null.

**Idempotency** — `POST /api/v2/sessions` honors an `Idempotency-Key` header (1–255 chars, trimmed;
blank → `422`). Scope is **per-org, 24h**:
- same key + same body → **replay**: original `Session` returned (`201`), no new run.
- same key + different body → `422` (conflict).
- same key while the first is still in flight → `409` + `Retry-After: 2`.
- Failed creates release the claim so the key can be retried (rare store failures make dedup
  best-effort — a retry may then duplicate).

**`overrides`** (on `SessionRequest`) patch the resolved request by dotted path; list members are
selected with `[field=value]`, e.g. `{"agent.environments[kind=web].start_url": "https://bing.com"}`.
Type-checked → `422` on mismatch. Useful for tweaking a stored agent per-run without redefining it.

**Other session semantics**:
- `404 Not an agentic session` = the id exists but is a bare trajectory (internal tooling), not a
  real agent session.
- `429` on create = concurrency quota (`Concurrent trajectory limit reached (active/limit)`, per
  user/org) or platform capacity. Check `GET /api/v2/sessions/quota` before mass-launching.
- `POST /{id}/share` returns `{"share_url": "/share/api/v1/trajectories/{id}"}` — a **path**, resolve
  it against the platform web origin.
- `GET /{id}/resources/{bucket}/{key}` → `302` to a presigned S3 URL (screenshots, files). Follow
  redirects (`curl -L`).
- `GET /` list `owner` scopes: `me` | `me-in-organization` (default) | `organization` |
  `me-or-organization`. Sessions created with an *inline* agent aren't matchable by the `agent` name
  filter (only catalog-id sessions are).

**Event stream** — `new_events` items are `{"type": "<EventClassName>", "data": {...}, "timestamp"}`.
The big one is `AgentEvent`, whose `data` **is** the inner event, discriminated by `data.kind`:
`policy_event` (assistant output + `tool_reqs[]`), `tool_result`, `observation_event` (screenshots
serialized to URL strings — fetch via `/resources`), `answer_event` (populates `latest_answer`),
`message_event`, `error_event`. Other top-level types: `AgentStarted`/`Completion`/`Error` (Completion
carries `reason`: finished/timed_out/stopped), `MetricsUpdate`, `ActiveStateChange` (drives `idle`),
`LiveViewUrlEvent` (transient in-run URL; the durable review link is the agent-view pattern —
[../extras/agent-view-replay.md](../extras/agent-view-replay.md)), `ChatMessage`. **`AgentErrorEvent`
rows are filtered out for non-H-employee callers.**

## Agents & skills — the catalog

Every row is **reserved** (H-owned `h/…`, world-readable) or **org-scoped** (only the creating org).
Reads return reserved rows + your org's rows; on a name collision your org's row **shadows** the
reserved one. The `h/` namespace and reserved rows are **read-only for org users — any write returns
`403`.** Names are lowercase kebab, ≤63 chars/segment, optional single `org/` prefix. The path
converter is `:path`, so namespaced names round-trip literally (`GET /api/v2/agents/h/researcher`).
Renames aren't supported: on `PUT`, body `name` must equal the URL id (else `400`); `409` on duplicate
create. An inline `Agent` needs `environments` *unless* `subagents` is set (pure orchestrator), and at
most one environment per `kind`. `answer_format` (a JSON Schema) makes the answer structured. Skill
`description`/`body` reject the system-prompt wrapper tags (`</skill>`, `{% endraw %}`, etc.) with `422`.

## Environments & vaults

- **`web` is the only public environment `kind`** (the managed Browser). `mode`: `visual` (act on
  screenshot coordinates) | `multimodal` (screenshots + page markdown) | `text` (read-only markdown,
  no screenshots; `page_chars` is **only** valid here). A `session_id` field exists on the Browser
  spec but is **runtime-only — never set it yourself**.
- **Vaults** (1Password etc.) are an env-manager proxy. Create/rotate-token are **not idempotent** — a
  retry after a 5xx may double-write; list before retrying a timed-out create. Token rotation is its
  own route (`PUT /{id}/token`), deliberately not part of `PATCH`. Vault↔session attachment is
  platform-managed (no public `vault_id` on `SessionRequest`).
- **Vault health**: `GET /{id}/health` returns `200` whenever the vault exists and env-manager is
  reachable — **branch on the `ok` field, not the status code** (`{"ok": false, "error": "..."}`).
- **Proxy errors**: env-manager's non-success responses are mirrored back verbatim (same code/body),
  so 4xx shapes on vault routes are env-manager's own. `502 env-manager unreachable` if the proxy call
  itself fails.

## MCP server

A thin MCP proxy over `/api/v2`, mounted at `/mcp` (streamable-HTTP, registry name
`io.github.hcompai/hai-agents`). Same auth: it reuses your `Authorization: Bearer hk-...` (missing
identity → tool error "authenticate with an 'hk-' key"). Tools: `run_agent` (creates a session, polls
~24s for an answer, else returns a handle), `wait_for_session`, `list_agents`, `send_message`,
`cancel_session`, `share_session`. Works today in bearer-header hosts (Cursor, VS Code, Claude Code);
OAuth-only hosts (Claude.ai web, ChatGPT) await the deferred OAuth 2.1 flow.

## Error shape

FastAPI-style `{"detail": "..."}` (or the standard validation list on `422`). Common: `400` malformed
identity/input · `401` no gateway identity · `403` write to a reserved/`h/` row · `404` not found / not
visible / not yours · `409` duplicate-on-create or idempotent-in-flight · `422` validation · `429`
quota · `204` on `/changes` = no new events (not an error).
