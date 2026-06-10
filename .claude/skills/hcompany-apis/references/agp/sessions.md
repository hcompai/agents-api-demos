# Agent Platform v2 — Sessions

One-line summary: reference for the v2 sessions API (`/api/v2/sessions` — create and drive agent sessions: submit messages, long-poll for events and answers, pause/resume/cancel, feedback, sharing, quota, and session-owned resources), with exact request/response shapes, status codes, and long-polling semantics.

## Table of contents

1. [Auth](#1-auth)
2. [Session model & lifecycle](#2-session-model--lifecycle)
3. [How to run an agent session (step by step)](#3-how-to-run-an-agent-session)
4. [Routes](#4-routes)
5. [`SessionRequest` body (create)](#5-sessionrequest-body)
6. [Long-polling semantics (`/changes`)](#6-long-polling-semantics)
7. [Event types & payload shapes](#7-event-types--payload-shapes)
8. [Idempotency](#8-idempotency)
9. [Pagination & filtering](#9-pagination--filtering)
10. [Error reference](#10-error-reference)

---

## 1. Auth

Clients call through the API gateway with an H API key:

```
Authorization: Bearer hk-...
```

The gateway validates the key and injects identity headers; the backend reads **only** gateway-injected `X-User-Sub` (user UUID) and `X-User-Org` (org UUID), plus optional `X-User-Role`, `X-User-Org-Role`, `X-User-Email`. **Direct callers never set `X-User-*` themselves.** Missing identity on a protected route → `401 {"detail": "Authentication required"}`; malformed UUIDs → `400 {"detail": "Invalid user or org ID"}`.

Read routes (`GET /{id}`, `/{id}/status`, `/{id}/changes`, `/{id}/events`, `/{id}/resources/...`) use **optional** auth: a session shared via `POST /{id}/share` is readable without credentials. Write routes (create, messages, pause/resume, cancel, force_answer, feedback, share) always require auth, and feedback/share additionally require user/org ownership (a merely-public session 404s).

## 2. Session model & lifecycle

A session is an interactive agent run (backed by a `Trajectory` row). `status` (`TrajectoryStatus`) values:

```
pending → running ⇄ idle            (idle = agent answered, waiting for follow-up)
            ↓ ⇅ paused
            → completed | failed | timed_out | interrupted   (terminal)
```

Terminal states: `completed`, `failed`, `timed_out`, `interrupted`. **Sending a message to a terminal session restarts it** (re-provisions the agent with its prior event history, subject to quota); sending to a `paused` session auto-resumes it.

`Session` (response envelope):

| field | type | notes |
|---|---|---|
| `id` | UUID | |
| `request` | `SessionRequest` | the original (resolved) create body |
| `status` | `SessionStatus` | see below |
| `latest_answer` | any | most recent final answer: free-form text, or structured data when the agent has an `answer_format`. `null` until the agent first answers |
| `created_at` / `started_at` / `finished_at` | datetime / nullable | |

`SessionStatus`:

| field | type | notes |
|---|---|---|
| `status` | `TrajectoryStatus` | lifecycle state |
| `error` | `string \| null` | failure message |
| `steps` | int | policy calls taken |
| `usage_per_model` | `ModelUsage[]` | `{name, input_tokens, output_tokens, reasoning_tokens}` |
| `subagent_session_ids` | `UUID[]` | child sessions spawned by this one |

`SessionSummary` (list items): `{id, agent (catalog name or inline-agent name, nullable), status, first_message (UserMessageEvent | null), created_at, started_at, finished_at}`.

## 3. How to run an agent session

**Step 1 — create the session** (`201`). Reference a stored agent by catalog name, or pass an inline definition:

```bash
curl -s -X POST https://agp.hcompany.ai/api/v2/sessions \
  -H "Authorization: Bearer $H_API_KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: run-2026-06-10-001" \
  -d '{
    "agent": {
      "name": "price-checker",
      "description": "Finds product prices on the web",
      "environments": [{"id": "browser", "kind": "web", "start_url": "https://www.bing.com"}]
    },
    "messages": "Find the current price of a Framework 13 laptop",
    "max_steps": 50,
    "max_time_s": 600,
    "idle_timeout_s": 300
  }'
# → 201 {"id": "8f0c...", "request": {...}, "status": {"status": "pending", ...}, "latest_answer": null, ...}
```

`messages` accepts a plain string, a single `UserMessageEvent`, or a list of either. With a stored agent: `"agent": "my-org-agent"` (string catalog id; the platform resolves it and every nested environment/skill/subagent reference).

As soon as you have the session `id`, give the user the browser view link — `https://platform.hcompany.ai/agent-view/{id}` (EU API → `platform.eu.hcompany.ai`) — so they can watch the run live and replay it afterwards ([../extras/agent-view-replay.md](../extras/agent-view-replay.md)).

**Step 2 — long-poll for events and the answer** (`GET /{id}/changes`). Keep a cursor `from_index` (count of events you have already seen); loop:

```bash
FROM=0
while true; do
  RESP=$(curl -s -w '\n%{http_code}' \
    "https://agp.hcompany.ai/api/v2/sessions/$ID/changes?from_index=$FROM&wait_for_seconds=30" \
    -H "Authorization: Bearer $H_API_KEY")
  CODE=$(tail -n1 <<<"$RESP"); BODY=$(sed '$d' <<<"$RESP")
  [ "$CODE" = 204 ] && continue                      # nothing new within 30s; poll again
  FROM=$((FROM + $(jq '.new_events | length' <<<"$BODY")))
  STATUS=$(jq -r .status <<<"$BODY")
  ANSWER=$(jq -r '.answer // empty' <<<"$BODY")
  [ -n "$ANSWER" ] && echo "answer: $ANSWER"
  case "$STATUS" in completed|failed|timed_out|interrupted) break;; esac
done
```

A `200` body is a `TrajectoryChanges` (§6) carrying `new_events`, the live `status`, and `answer` once the agent emits one. Non-interactive alternative: skip `/changes` and poll `GET /{id}` until `status.status` is terminal or `idle`, then read `latest_answer`.

**Step 3 — converse (optional)** (`202`, empty body):

```bash
curl -s -X POST "https://agp.hcompany.ai/api/v2/sessions/$ID/messages" \
  -H "Authorization: Bearer $H_API_KEY" -H "Content-Type: application/json" \
  -d '{"type": "user_message", "message": "Only consider the 32GB model."}'
```

Then continue long-polling from your cursor. To force a wrap-up: `POST /{id}/force_answer` (the agent emits a final answer on its next step).

**Step 4 — terminate**. With an `idle_timeout_s` the session lingers in `idle` after each answer waiting for follow-ups (without it, the session ends at the first answer). End it explicitly:

```bash
curl -s -X DELETE "https://agp.hcompany.ai/api/v2/sessions/$ID" \
  -H "Authorization: Bearer $H_API_KEY"      # → 204; status becomes "interrupted"
```

## 4. Routes

All paths below are prefixed `https://agp.hcompany.ai/api` (router mount: `/v2/sessions`). Errors are FastAPI-shaped: `{"detail": "..."}` (or the standard FastAPI validation list on 422).

### POST `/api/v2/sessions` — create a session
- Body: `SessionRequest` (§5). Optional header `Idempotency-Key` (1–255 chars, trimmed; §8).
- `201` → `Session`. Status starts `pending`; provisioning is async.
- Errors: `400` invalid request (trajectory creation rejected), `404` `Agent '<artifact>' not found.` (unusable `agent_artifact`), `409` idempotent request in flight (`Retry-After: 2`), `422` blank/oversized `Idempotency-Key`, key reused with different body, or invalid `overrides` path/type, `429` concurrency quota: per-user/org limit (`Concurrent trajectory limit reached (active/limit)`) or platform-wide capacity.

### GET `/api/v2/sessions` — list sessions
- Query params: §9. `200` → `Page[SessionSummary]` = `{items: SessionSummary[], total: int, page: int}`.

### GET `/api/v2/sessions/quota` — concurrent-session quota
- `200` → `QuotaStatus`: `{scope: "user" | "org", limit: int, active: int, available: int}`.

### GET `/api/v2/sessions/{id}` — get a session
- Optional auth (public sessions readable unauthenticated). `200` → `Session`. `404` `Session not found` / `Not an agentic session` (id exists but is a bare trajectory, e.g. created by internal tooling).

### GET `/api/v2/sessions/{id}/status` — live status
- Optional auth. `200` → `SessionStatus`. Cheaper than `GET /{id}` for status polling. `404` as above.

### DELETE `/api/v2/sessions/{id}` — cancel
- `204`, empty. Stops the agent; status → `interrupted`. Idempotent in effect.

### POST `/api/v2/sessions/{id}/messages` — send message(s)
- Body (discriminated on `type`): a single `UserMessageEvent` —

  ```json
  {"type": "user_message", "message": "text", "images": ["data:image/png;base64,..."], "caller_id": "user"}
  ```

  (`images` and `caller_id` optional) — or a batch (min 1 message, no nested batches):

  ```json
  {"type": "batch", "messages": [{"type": "user_message", "message": "a"}, {"type": "user_message", "message": "b"}]}
  ```
- `202`, empty body (fire-and-forget; the message echoes back later as a trajectory event). Restarts a terminal session; auto-resumes a paused one. Messages sent while `pending` are buffered until the agent starts.

### POST `/api/v2/sessions/{id}/pause` — pause
### POST `/api/v2/sessions/{id}/resume` — resume
### POST `/api/v2/sessions/{id}/force_answer` — request a final answer
- All three: no body, `202`, empty response. `force_answer` sends `{"type": "flow_control", "flow": "force_answer"}` to the agent; watch `/changes` for the resulting answer.

### GET `/api/v2/sessions/{id}/changes` — long-poll for new events
- Optional auth. Query params:

| param | type | default | notes |
|---|---|---|---|
| `from_index` | int | `0` | number of events already seen (cursor); negative values clamp to 0 |
| `limit` | int ≥ 0 | none | max events returned this call |
| `include_events` | bool | `true` | `false` → `new_events: []` but still 200-vs-204 gated on event arrival |
| `wait_for_seconds` | int, 0–60 | `0` | long-poll window; see §6 |

- `200` → `TrajectoryChanges` (§6). `204` (empty body, header `ETag: <from_index>`) when no new events exist after waiting. Values of `wait_for_seconds` above the server cap (`ApiConfig.long_poll_max_wait_for_seconds`, default 60) → `422`.

### GET `/api/v2/sessions/{id}/events` — paginated event history
- Optional auth. Query: `page` (int ≥ 1, default 1), `size` (1–200, default 50), `sort` (repeatable: `timestamp` | `-timestamp`; default ascending; ties broken by `index`), `type` (exact event-type filter, e.g. `AgentEvent`).
- `200` → `Page[TrajectoryEvent]`. Use `/changes` for live tailing; this is for replay/inspection. `AgentErrorEvent` rows are hidden from non-H-employee callers.

### POST `/api/v2/sessions/{id}/feedback` — session feedback
- Body `Feedback`: `{"success": true, "message": "optional text"}` (`message` nullable). `204`. Requires ownership (`404` on shared-only access).

### PUT `/api/v2/sessions/{id}/events/{event_index}/feedback` — per-event feedback
- Same `Feedback` body. `204`. `404` `Event not found` if `event_index` is out of range.

### POST `/api/v2/sessions/{id}/share` — make public
- No body. `200` → `{"share_url": "/share/api/v1/trajectories/{id}"}` (a path; resolve against the platform web origin). Anyone can then read the session unauthenticated.

### DELETE `/api/v2/sessions/{id}/share` — revoke public access
- `204`, empty.

### GET `/api/v2/sessions/{id}/resources/{bucket}/{key}` — fetch a session resource
- Optional auth; `key` may contain slashes (path-typed). `302` redirect to a presigned S3 URL for a session-owned resource (screenshots, files referenced by event payloads). Access is validated against the session; follow redirects (`curl -L`).

## 5. `SessionRequest` body

`extra` fields are rejected. Fields:

| field | type | required | notes |
|---|---|---|---|
| `agent` | `string \| Agent` | yes | registered agent's name (catalog id), or an inline `Agent` definition. Non-empty |
| `messages` | `string \| UserMessageEvent \| UserMessageEvent[] \| null` | no | initial task, queued before turn 1. A bare string becomes `{"type": "user_message", "message": ...}` |
| `max_steps` | `int ≥ 1 \| null` | no | cap on reasoning steps; unbounded if null |
| `max_time_s` | `float > 0 \| null` | no | wall-clock cap (becomes the trajectory timeout) |
| `idle_timeout_s` | `int > 0 \| null` | no | seconds to keep the session open for follow-ups after each answer; null ends the session at the first answer |
| `group_id` | `string \| null` | no | groups related sessions for listing |
| `parent_session_id` | `string \| null` | no | marks this as a child run (shows in parent's `subagent_session_ids`) |
| `agent_artifact` | `string \| null` | no | target agent-runtime artifact version; platform default if null. `404` if not usable by the caller |
| `overrides` | `dict<string, any>` | no | per-run overrides on the resolved request, keyed by dotted path; list members selected with `[field=value]`, e.g. `{"agent.environments[kind=web].start_url": "https://bing.com"}`. Type-checked → `422` on mismatch |

Inline `Agent` (same shape as the `/api/v2/agents` catalog; every nested string reference is resolved at create time):

| field | type | required | notes |
|---|---|---|---|
| `name` | string (1–127) | yes | lowercase kebab segments, optional single `org/` prefix |
| `description` | string | yes | read by parent agents when delegating |
| `environments` | `(string \| Environment)[]` | yes* | catalog ids or inline specs; at most one per `kind` (`web` is the public kind — shape in the environments reference). *Optional only when `subagents` is set (pure orchestrator) |
| `model` | `string \| null` | no | platform default if omitted |
| `instructions` | `string \| null` | no | appended to the system prompt |
| `subagents` | `(string \| Agent)[] \| null` | no | names or inline definitions of delegatable agents |
| `skills` | `(string \| Skill)[] \| null` | no | names or inline skills (`{name, description, body, source?, url_pattern?}`) |
| `answer_format` | `JSON Schema object \| null` | no | schema the final answer must conform to; null → free-form text. Drives structured `latest_answer` / `answer` |

## 6. Long-polling semantics

`GET /{id}/changes?from_index=N&wait_for_seconds=S`:

- If more than `N` events already exist, the call returns immediately with `200`.
- Otherwise the server subscribes to the session's change notifications (Redis) and waits up to `S` seconds (`0` = no wait; server cap **60s** — `ApiConfig.long_poll_max_wait_for_seconds`, env-configurable per deployment).
- If nothing arrives in time: **`204 No Content`** with empty body and header `ETag: <from_index>`. This is the normal "keep polling" signal, not an error.
- On `200`, the body is `TrajectoryChanges`:

| field | type | notes |
|---|---|---|
| `status` | `TrajectoryStatus` | current lifecycle state |
| `started_at` / `finished_at` | datetime \| null | |
| `error` | `string \| null` | only populated for H-employee callers; otherwise always null |
| `new_events` | `TrajectoryEvent[]` | events after `from_index`, ordered by `(timestamp, index)`; `[]` when `include_events=false` |
| `answer` | `string \| object \| null` | latest final answer (object when `answer_format` is set) |
| `metrics` | `Metrics` | `{steps, cost_per_model: ModelCost[], input_cost, output_cost, reasoning_cost, total_cost}` |

- **Cursor rule:** next `from_index` = previous `from_index` + `len(new_events)`. The cursor is an event *count*, not an event id.
- Stop polling when `status` is terminal (`completed`, `failed`, `timed_out`, `interrupted`) **and** you've drained `new_events` — or, for chat-style usage, treat `idle` + a fresh `answer` as "the agent's turn is done".
- `404` before any wait if the id is unknown / not visible / not an agentic session (access is checked before subscribing).

## 7. Event types & payload shapes

Wire shape (every element of `new_events` / `/events` items):

```json
{"type": "<EventClassName>", "data": { ... }, "timestamp": "2026-06-10T12:00:00Z"}
```

Top-level `type` values:

| `type` | `data` payload | meaning |
|---|---|---|
| `AgentStartedEvent` | runtime start info | agent pod started; status `pending → running` |
| `AgentCompletionEvent` | includes `reason`: `"finished" \| "timed_out" \| "stopped"` | run ended → `completed` / `timed_out` / `interrupted` |
| `AgentErrorEvent` | `{error, ...}` | run failed → `failed`. **Filtered out for non-H-employee callers** |
| `AgentEvent` | the inner agent event, flattened (see below) | a step of the agent loop |
| `MetricsUpdateEvent` | `{metrics: {steps, cost_per_model, ...}}` | usage/cost refresh |
| `ActiveStateChangeEvent` | `{state: "running" \| "idle"}` | agent went busy/idle (drives `idle` status) |
| `LiveViewUrlEvent` | `{url}` | transient in-run live-browser URL; the durable review link is the agent-view pattern ([../extras/agent-view-replay.md](../extras/agent-view-replay.md)) |
| `ChatMessageEvent` | chat payload (may carry a `screenshot`) | agent-authored chat message |

For `AgentEvent`, the API flattens the stored record so `data` **is** the inner event, discriminated by `data.kind`:

| `data.kind` | key fields |
|---|---|
| `policy_event` | `message` (assistant LLM output), `tool_reqs[]` (`{tool_name, args, ...}`), `validation_errors[]` |
| `tool_result` | `tool_req`, `result` |
| `observation_event` | `text?`, `observation` (web/computer screenshot observation; screenshot fields are serialized to URL strings — fetchable via `/{id}/resources/...`) |
| `answer_event` | `answer` (string or structured object), `context` (thoughts/notes) — this is what populates `latest_answer` |
| `message_event` | `caller_id`, `content[]` (text and image parts) — echoes of user messages and agent chat |
| `error_event` | `error`, `origin`, `traceback?`, `tool_req?`, `info?` |

`data.pre_action_screenshot` / `data.post_action_screenshot`, when present, are pre-serialized to URL strings.

## 8. Idempotency

`POST /api/v2/sessions` accepts an `Idempotency-Key` header (1–255 chars; whitespace-trimmed; blank → `422 Idempotency-Key must not be blank`). Scope: per organization, 24h window.

| situation | result |
|---|---|
| first use | session created normally (`201`) |
| same key + same body within 24h | **replay**: the original `Session` is returned (`201`), no new session |
| same key + different body | `422` (`IdempotencyKeyConflict` message) |
| same key while the first request is still in flight | `409 {"detail": "Idempotency-Key request in flight; retry shortly"}` + `Retry-After: 2` |

If creation fails, the claim is released so the key can be retried. On a rare store failure after creation, dedup is best-effort (a retry may create a duplicate).

## 9. Pagination & filtering

`GET /api/v2/sessions` query parameters (all optional):

| param | type | default | notes |
|---|---|---|---|
| `page` | int ≥ 1 | `1` | 1-based |
| `size` | int 1–100 | `10` | |
| `sort` | repeatable: `created_at` \| `-created_at` | `-created_at` | |
| `owner` | `me` \| `me-in-organization` \| `organization` \| `me-or-organization` | `me-in-organization` | visibility scope |
| `status` | repeatable `TrajectoryStatus` | — | e.g. `?status=running&status=idle` |
| `agent` | repeatable string | — | matches the catalog-id string in the stored request; sessions created with an *inline* agent are not matchable by name |
| `group_id` | string | — | exact |
| `parent_session_id` | string | — | exact; lists a session's children |
| `search` | string | — | case-insensitive substring on the session's first message/objective **or** its answer |
| `created_before` / `created_after` | ISO datetime | — | strict `<` / `>` |
| `finished_before` / `finished_after` | ISO datetime | — | strict `<` / `>` |

Response: `Page[SessionSummary]` = `{items, total, page}`. `/{id}/events` pagination is described in §4.

## 10. Error reference

| code | where | meaning |
|---|---|---|
| `400` | any | malformed identity headers; invalid trajectory creation input |
| `401` | protected routes | no gateway identity (bad/missing API key) |
| `404` | most routes | session not found, not visible to you, not an agentic session, agent artifact not found, event index out of range, or a write (feedback/share) on a session you don't own |
| `409` | create | idempotent request in flight (`Retry-After: 2`) |
| `422` | create, `/changes` | validation errors (FastAPI list shape), idempotency key blank/conflict, invalid `overrides`, `wait_for_seconds` over the cap |
| `429` | create | concurrent-session quota exhausted (user/org limit or platform capacity) |
| `204` | `/changes` | **not an error** — no new events within the wait window (`ETag` echoes `from_index`) |
