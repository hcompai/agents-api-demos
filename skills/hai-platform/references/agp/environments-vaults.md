# Agent Platform v2 — Environments & Vaults

One-line summary: reference for the v2 environment catalog (`/api/v2/environments` — declarative specs for the browser environments an agent runs in) and the vault-config proxy (`/api/v2/vaults` — third-party secret providers, currently 1Password, that sessions use to fill credentials), with exact request/response shapes, status codes, and auth behavior.

## Table of contents

1. [Auth (applies to every route here)](#1-auth)
2. [What an environment is](#2-what-an-environment-is)
3. [Environment spec shapes (request/response body)](#3-environment-spec-shapes)
4. [Environments routes](#4-environments-routes)
5. [Environment visibility & the reserved `h/` namespace](#5-environment-visibility--the-reserved-h-namespace)
6. [What a vault is](#6-what-a-vault-is)
7. [Vaults routes (env-manager proxy)](#7-vaults-routes-env-manager-proxy)
8. [Vault model shapes](#8-vault-model-shapes)
9. [Proxy error semantics](#9-proxy-error-semantics)

---

## 1. Auth

Clients call through the API gateway with an H API key:

```
Authorization: Bearer hk-...
```

The gateway validates the key and injects identity headers; the backend reads **only** `X-User-Sub` (user UUID) and `X-User-Org` (org UUID), plus optional `X-User-Role`, `X-User-Org-Role`, `X-User-Email`. **Direct callers never set `X-User-*` themselves** — they are gateway-injected. Missing identity → `401 {"detail": "Authentication required"}`; malformed UUIDs in the headers → `400 {"detail": "Invalid user or org ID"}`.

---

## 2. What an environment is

An environment is a **catalog entry**: a named, declarative spec describing a capability surface a session provisions for the agent. It is *not* a running instance. One public kind (`EnvironmentKind`):

| `kind` | Model | What the agent gets |
|---|---|---|
| `web` | `Browser` | A web browser it navigates and acts on (screenshots/coordinates, markdown text, or both) |

Server-side, each catalog row stores the spec as JSON plus `description`, `reserved`, `org_id`, `user_id`, `created_at`, `updated_at` — but the **API request and response body is the bare spec only** (the `Environment` union, keyed on `kind`). Timestamps/ownership are not returned.

## 3. Environment spec shapes

Every spec has `id` (catalog identifier, min length 1; may contain slashes, e.g. `h/browser-default`) and the `kind` discriminator (`web` is the only public kind).

**`web` (Browser)** — defaults shown:

```json
{
  "id": "my-browser",
  "kind": "web",
  "headless": false,
  "width": 1200,
  "height": 1200,
  "start_url": "https://www.bing.com",
  "mode": "visual",
  "page_chars": 20000
}
```

- `mode`: `"visual"` (act on screenshots by viewport coordinates) | `"multimodal"` (screenshots + page markdown) | `"text"` (read-only markdown, URL navigation, no screenshots).
- `page_chars` (int > 0): characters of page text per page — **only valid with `mode: "text"`**; setting it with another mode is a validation error.
- `width`/`height` must be > 0.
- Note: a `session_id` field exists internally on the Browser spec but is runtime-only (set by the platform) — never set it yourself.

## 4. Environments routes

All paths below are relative to the base, e.g. `https://agp.hcompany.ai/api`. Body validation failures return FastAPI's standard `422` with a `detail` array.

| Method | Path | Purpose | Success |
|---|---|---|---|
| POST | `/api/v2/environments` | Create a catalog environment | `201` → spec |
| GET | `/api/v2/environments` | Paginated list (reserved + own org) | `200` → `EnvironmentPage` |
| GET | `/api/v2/environments/{id}` | Fetch by catalog id (`:path` — slashes allowed) | `200` → spec |
| PUT | `/api/v2/environments/{id}` | Full-replace the spec | `200` → spec |
| DELETE | `/api/v2/environments/{id}` | Delete by catalog id | `204` |

### POST /api/v2/environments

Body: one `Environment` spec (see §3). Response `201`: the stored spec, same shape.

Errors:
- `403` — `id` starts with `h/` (the `h/` namespace is read-only for org users): `{"detail": "Reserved environments and the 'h/' namespace are restricted to H employees."}`
- `409` — duplicate catalog id (unique per org; reserved ids globally unique): `{"detail": "Environment 'my-browser' already exists."}`
- `422` — spec validation (unknown `kind`, bad field values, …).

### GET /api/v2/environments

Query parameters:

| Param | Type | Default | Meaning |
|---|---|---|---|
| `page` | int ≥ 1 | `1` | Page number (1-based) |
| `size` | int 1–1000 | `10` | Items per page |
| `sort` | repeatable enum | `-created_at` | One of `created_at`, `-created_at`, `id`, `-id` (`id` sorts on the catalog id, i.e. `spec->id`) |
| `id` | string | — | Case-insensitive **substring** match on catalog id |
| `kind` | enum | — | `web` |
| `search` | string | — | Case-insensitive substring match on catalog id **or** the row's description |

Response `200` (`EnvironmentPage`):

```json
{
  "items": [ {"id": "h/browser-default", "kind": "web", "...": "..."} ],
  "total": 42,
  "page": 1
}
```

### GET /api/v2/environments/{id}

`{id}` is the **catalog id** (not a UUID) and is declared `{id:path}`, so slash-containing ids like `h/browser-default` round-trip without encoding. `200` → the spec. `404 {"detail": "Environment 'x' not found."}` if no visible row.

### PUT /api/v2/environments/{id}

Body: a complete `Environment` spec — this is a full replace, not a patch. Constraints:
- `400` if `spec.id` ≠ URL id: `{"detail": "spec.id 'a' does not match URL identifier 'b'."}`
- `404` if not visible (or org-owned by a different org).
- `403` if the row is reserved (read-only for org users): `{"detail": "Environment 'x' is reserved; only H employees can modify it."}`
- `reserved` is immutable; only `spec` (+ `updated_at`) is written.

`200` → the updated spec.

### DELETE /api/v2/environments/{id}

`204` on success, no body. `404` if not visible; `403` if the row is reserved (read-only for org users): `{"detail": "Environment 'x' is reserved; only H admins can delete it."}`

## 5. Environment visibility & the reserved `h/` namespace

- **Visible** = all `reserved=true` rows (H-owned, world-readable, the bundled catalog) **plus** the caller's own org rows.
- The `h/` namespace and reserved rows are **read-only for org users**: any write (create, update, delete) returns `403`.
- On id collision an org's own row **shadows** the reserved one of the same id for that org's reads; other orgs still see the reserved row.
- Uniqueness: catalog id unique among reserved rows; unique per `(id, org_id)` among org rows.

---

## 6. What a vault is

A **vault config** points the env-manager (session manager, `agent-environments` service) at a **third-party secret provider** — currently only **1Password**. Once a vault is attached to a session, the session runner's `fill_secret_*` / `list_secrets` commands resolve credentials against it (e.g. a browser agent logging into a site without the secrets ever entering the prompt). Caveat: the public `SessionRequest` schema exposes no `vault_id` field — session attachment is platform-managed (session reads embed a compact `VaultSummary`); before promising users a session-create binding field, verify the live schema at `/share/openapi.json`. The provider token (`ops_...` service-account token for 1Password) is **write-only**: sent on create and rotate, validated against the provider before storage, and never returned by any read endpoint.

AgP does not own vault state: `/api/v2/vaults` (`hplatform/controller/vaults.py`) is a thin proxy that forwards each call to env-manager's `/v1/vaults` API (`ENVIRONMENT_MANAGER_URL` setting), re-asserting the caller's identity per request via the same `X-User-*` headers (env-manager runs in `auth_headers` trust mode). Responses are validated through the published `hai_drivers.common.vaults` SDK models before being returned. Vaults are org-scoped (each `VaultConfigRead` carries `org_id`); env-manager enforces authorization.

## 7. Vaults routes (env-manager proxy)

| Method | Path | Forwards to (env-manager) | Success |
|---|---|---|---|
| POST | `/api/v2/vaults` | `POST /v1/vaults` | `201` → `VaultConfigRead` |
| GET | `/api/v2/vaults` | `GET /v1/vaults` | `200` → `VaultConfigList` |
| GET | `/api/v2/vaults/{vault_id}` | `GET /v1/vaults/{vault_id}` | `200` → `VaultConfigRead` |
| PATCH | `/api/v2/vaults/{vault_id}` | `PATCH /v1/vaults/{vault_id}` | `200` → `VaultConfigRead` |
| PUT | `/api/v2/vaults/{vault_id}/token` | `PUT /v1/vaults/{vault_id}/token` | `204` |
| DELETE | `/api/v2/vaults/{vault_id}` | `DELETE /v1/vaults/{vault_id}` | `204` |
| GET | `/api/v2/vaults/{vault_id}/health` | `GET /v1/vaults/{vault_id}/health` | `200` → `VaultHealth` |

`{vault_id}` is a UUID (422 if not).

### POST /api/v2/vaults — create

```json
{
  "name": "my-1p",
  "provider_config": {"provider": "onepassword", "op_vault_id": "abc123"},
  "token": "ops_..."
}
```

env-manager validates the token against the provider before storing; `201` → `VaultConfigRead`. **Not idempotent**: a retry after a 5xx may double-write — treat retries as unsafe. The plaintext token is forwarded explicitly and never logged.

### GET /api/v2/vaults — list

Query: `limit` (int 1–1000, default `50`), `offset` (int ≥ 0, default `0`). Offset-based — note this differs from the page/size pagination used by environments. `200` → `VaultConfigList`.

### PATCH /api/v2/vaults/{vault_id} — partial update

Body (both optional; only fields actually present are forwarded — `exclude_unset`):

```json
{"name": "renamed", "provider_config": {"provider": "onepassword", "op_vault_id": "xyz789"}}
```

Token rotation is deliberately **not** part of PATCH. `200` → updated `VaultConfigRead`.

### PUT /api/v2/vaults/{vault_id}/token — rotate token

Body: `{"token": "ops_new..."}`. env-manager health-checks the new token before writing. `204`, no body. Same non-idempotency caveat as create.

### GET /api/v2/vaults/{vault_id}/health — probe provider

Returns `200` whenever the vault exists and env-manager is reachable — **branch on `ok`, not the status code**:

```json
{"ok": false, "error": "1Password: invalid service account token"}
```

### DELETE /api/v2/vaults/{vault_id}

`204`, no body.

## 8. Vault model shapes

From `hai_drivers.common.vaults`:

```json
// VaultConfigRead — never includes the stored token
{
  "id": "0c9f8a4e-3a1b-4f7e-9d2c-1e5f6a7b8c9d",
  "org_id": "7b1e2d3c-4f5a-6b7c-8d9e-0f1a2b3c4d5e",
  "name": "my-1p",
  "provider_config": {"provider": "onepassword", "op_vault_id": "abc123"},
  "created_at": "2026-06-01T12:00:00Z",
  "updated_at": "2026-06-01T12:00:00Z"
}

// VaultConfigList
{"total": 3, "limit": 50, "offset": 0, "vaults": [ /* VaultConfigRead... */ ]}

// VaultHealth
{"ok": true, "error": null}
```

`ProviderConfig` is currently the single `OnePasswordConfig` shape (`provider: "onepassword"`, `op_vault_id: str`); it becomes a discriminated union when more providers ship. `VaultSummary` (`id`, `name`, `provider`) is the compact form embedded in session reads.

## 9. Proxy error semantics

From `hplatform/controller/utils/env_manager_proxy.py`:

- **Non-success env-manager responses are mirrored back verbatim** — same status code, same body bytes, same `Content-Type` (via `EnvManagerError`, specifically to avoid double-nesting env-manager's own `{"detail": ...}`). So 401/403/404/409/422 shapes on vault routes are env-manager's, passed through unchanged.
- **`502 {"detail": "env-manager unreachable"}`** if the HTTP call to env-manager fails (connection error, timeout).
- Success bodies are re-validated against the SDK models above before being returned; `204` routes return nothing.
- Identity forwarding: every proxied request carries `X-User-Sub` and `X-User-Org`, plus `X-User-Role` / `X-User-Org-Role` / `X-User-Email` when present, rebuilt per request (multi-tenant).
