# Agent Platform v2 API — Agents & Skills

CRUD reference for the v2 catalog routers: `/api/v2/agents` and `/api/v2/skills` (production base `https://agp.hcompany.ai/api`).

## Table of contents

- [Authentication & scoping](#authentication--scoping)
- [Pagination](#pagination)
- [Agents](#agents)
  - [The Agent resource](#the-agent-resource)
  - [POST /api/v2/agents](#post-apiv2agents)
  - [GET /api/v2/agents](#get-apiv2agents)
  - [GET /api/v2/agents/{agent_name}](#get-apiv2agentsagent_name)
  - [PUT /api/v2/agents/{agent_name}](#put-apiv2agentsagent_name)
  - [DELETE /api/v2/agents/{agent_name}](#delete-apiv2agentsagent_name)
- [Skills](#skills)
  - [The Skill resource](#the-skill-resource)
  - [POST /api/v2/skills](#post-apiv2skills)
  - [GET /api/v2/skills](#get-apiv2skills)
  - [GET /api/v2/skills/{name}](#get-apiv2skillsname)
  - [PUT /api/v2/skills/{name}](#put-apiv2skillsname)
  - [DELETE /api/v2/skills/{name}](#delete-apiv2skillsname)
- [Common error responses](#common-error-responses)

## Authentication & scoping

Clients call through the gateway with an H API key:

```
Authorization: Bearer hk-...
```

The backend never sees the key. The gateway validates it and injects identity headers — `X-User-Sub` (user UUID), `X-User-Org` (org UUID), plus `X-User-Role`, `X-User-Org-Role`, `X-User-Email` — which the backend reads to build the request identity. **Direct callers never set those headers themselves.** Missing identity yields `401 {"detail": "Authentication required"}`; malformed UUIDs yield `400 {"detail": "Invalid user or org ID"}`.

**Ownership / visibility model (agents, skills, environments):**

- Every catalog row is either **reserved** (H-owned built-ins, world-readable) or **org-scoped** (visible only to the creating org).
- Reads return reserved rows + the caller's org rows. On a name collision, the org's own row **shadows** the reserved one for that org's callers.
- The `h/` namespace and reserved rows are **read-only for org users**: any write (create, update, delete) to an `h/`-prefixed name or a reserved row returns `403`.
- Writes to another org's row return `404` (indistinguishable from missing).

## Pagination

List endpoints share query parameters and a `Page` envelope:

| Param | Type | Default | Notes |
|---|---|---|---|
| `page` | int >= 1 | `1` | 1-based page number |
| `size` | int 1–1000 | `10` | items per page |
| `sort` | list[str] | per-route | repeatable; prefix `-` for descending; values outside the per-route allowlist are `422` |

Response envelope:

```json
{ "items": [ ... ], "total": 42, "page": 1 }
```

## Agents

Router: `/api/v2/agents` (tag `Agents`). Resource type: `Agent` spec from `agent_interface.specs.agent`. Stored as a JSON `spec` column; the wire shape **is** the spec — no server-side `id` or timestamps are exposed. `created_at`/`updated_at` exist on the row only for sorting.

### The Agent resource

A declarative agent definition:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | str (1–127) | yes | Unique catalog name. Lowercase ASCII letters/digits/hyphens, alphanumeric at both ends, max 63 chars per segment, optional single `org/` namespace prefix (e.g. `h/researcher`). |
| `description` | str (min 1) | yes | What the agent does; parent agents read this to decide when to delegate. |
| `environments` | list[str \| Environment] | yes (may be `[]` only if `subagents` set) | Where the agent runs. Each entry is a registered environment **id** (string ref) or an inline Environment object. At most one per `kind`; duplicate string ids rejected. A pure orchestrator (with `subagents`) may have `[]`. |
| `model` | str \| null | no | Model serving the agent; platform default if omitted. |
| `instructions` | str \| null | no | Text appended to the agent's system prompt. |
| `subagents` | list[str \| Agent] \| null | no | Agents this one can delegate to — registered agent name or inline Agent. |
| `skills` | list[str \| Skill] \| null | no | Skills available — registered skill name or inline Skill. |
| `answer_format` | object \| null | no | JSON Schema the final answer must conform to (validated as a JSON Schema; invalid → 422). `null` = free-form text answer. |

Inline `Environment` objects are a discriminated union on `kind`; the public kind is `web` (Browser: `id`, `headless`, `width`, `height`, `start_url`, `mode` = `visual`/`text`/`multimodal`, `page_chars`). Note: a `session_id` field exists internally on the Browser spec but is runtime-only (set by the platform) — never set it yourself.

```json
{
  "name": "acme/researcher",
  "description": "Researches a topic on the web and reports findings.",
  "model": null,
  "instructions": "Cite sources for every claim.",
  "environments": [
    { "id": "browser", "kind": "web", "headless": true, "width": 1280, "height": 720,
      "start_url": "https://www.bing.com", "mode": "visual", "page_chars": 20000 }
  ],
  "skills": ["acme/sec-filings", { "name": "inline-tip", "description": "Use on news sites", "body": "Prefer the print view." }],
  "subagents": null,
  "answer_format": { "type": "object", "properties": { "summary": { "type": "string" } } }
}
```

### POST /api/v2/agents

Create an agent. Request body: full `Agent` spec. Response: `201` with the stored spec echoed back.

Errors: `409` `Agent '<name>' already exists.` (unique per org; reserved names globally unique) · `403` for `h/`-prefixed names (the `h/` namespace is read-only) · `422` on spec validation (bad name format, missing `environments` without `subagents`, >1 environment per kind, invalid `answer_format` schema).

### GET /api/v2/agents

List reserved + caller's-org agents. Returns `Page[Agent]`.

Query params: pagination (above) plus:

| Param | Description |
|---|---|
| `sort` | one of `created_at`, `-created_at`, `agent_name`, `-agent_name` (default `-created_at`); `agent_name` sorts on `spec.name` |
| `agent_name` | case-insensitive substring match on agent name |
| `search` | case-insensitive match on agent name **or** description |

```
GET /api/v2/agents?page=1&size=20&sort=-created_at&search=research
```

### GET /api/v2/agents/{agent_name}

Fetch by name. The path converter is `:path`, so namespaced names round-trip literally: `GET /api/v2/agents/h/researcher`.

| Query | Default | Meaning |
|---|---|---|
| `resolve` | `false` | When `true`, recursively materialises every **string** environment/skill/subagent reference into its full spec. |

Errors: `404` if not visible to the caller. With `resolve=true`: `404` if a referenced name doesn't resolve, `422` on a subagent cycle (`Subagent cycle detected: a -> b -> a.`) or nesting deeper than 16 levels.

### PUT /api/v2/agents/{agent_name}

Full replace of the spec. Body: complete `Agent`; `spec.name` **must equal** the URL identifier — renames are not supported (`400` `spec.name '...' does not match URL identifier '...'`). The `reserved` flag is immutable.

Errors: `400` name mismatch · `404` not visible / other org · `403` reserved row (read-only) · `422` validation. Returns `200` with the updated spec.

### DELETE /api/v2/agents/{agent_name}

Delete by name. `204` on success. `404` if not visible; `403` if the row is reserved (read-only for org users).

## Skills

Router: `/api/v2/skills` (tag `Skills`). A skill is **named, reusable Markdown instruction content** an agent loads during a session — referenced from `Agent.skills` by name or inlined.

### The Skill resource

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | str (min 1) | yes | Catalog name; same format rules as agent names (`h/` prefix reserved). Immutable after create. |
| `description` | str (min 1) | yes | When to use the skill — the agent reads this to decide whether to load it. |
| `body` | str (min 1) | yes | Markdown instructions injected when the skill is used. |
| `source` | str \| null | no | Provenance URL (max 2048 chars in storage). |
| `url_pattern` | str \| null (1–1024) | no | Regex hinting at URLs where the skill applies; must compile or `422`. |

Markup guards: `description` and `body` reject the Jinja `{% endraw %}` sequence and the closing tags `</skill>`, `</name>`, `</description>`, `</instructions>` (reserved for the system-prompt wrapper) with `422`.

**No versioning**: `PUT` is a full in-place replace; only the latest content is stored (`updated_at` is tracked internally but not exposed — the wire shape has no id or timestamps).

```json
{
  "name": "acme/sec-filings",
  "description": "Use when reading SEC EDGAR filings.",
  "body": "## EDGAR tips\nAlways open the 10-K index first...",
  "source": "https://internal.acme.test/playbooks/edgar",
  "url_pattern": "sec\\.gov/cgi-bin"
}
```

### POST /api/v2/skills

Create a skill. Body: full `Skill`. Response: `201` with the stored skill.

Errors: `409` `Skill '<name>' already exists.` · `403` for `h/`-namespace names (read-only) · `422` validation (markup guards, bad regex, name format).

### GET /api/v2/skills

List reserved + caller's-org skills. Returns `Page[Skill]`.

| Param | Description |
|---|---|
| `sort` | one of `created_at`, `-created_at`, `name`, `-name` (default `-created_at`) |
| `name` | case-insensitive substring match on skill name |
| `search` | case-insensitive match on skill name **or** description |

### GET /api/v2/skills/{name}

Fetch by name (`:path` converter, so `GET /api/v2/skills/h/web-tips` works). `404` if not visible.

### PUT /api/v2/skills/{name}

Full replace of `description`, `body`, `source`, `url_pattern`. Body `name` must match the URL identifier (`400` otherwise); renames not supported. `200` with the updated skill. `404` not visible / other org; `403` reserved row (read-only).

### DELETE /api/v2/skills/{name}

`204` on success. `404` not visible; `403` if the row is reserved (read-only for org users).

## Common error responses

All errors are FastAPI-style `{"detail": "..."}` JSON:

| Code | When |
|---|---|
| `400` | `spec.name`/`name` body–URL mismatch on PUT; invalid identity-header UUIDs |
| `401` | gateway identity missing (bad/absent `hk-` key) |
| `403` | write to a reserved row or the `h/` namespace (read-only for org users) |
| `404` | not found, not visible, or owned by another org (deliberately indistinguishable) |
| `409` | duplicate agent/skill name on create |
| `422` | Pydantic validation: name format, skill markup guards, bad `url_pattern`/`answer_format`, env-per-kind rule, subagent cycles/depth on `resolve=true`, disallowed `sort` values |
