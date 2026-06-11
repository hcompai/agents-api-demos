# API Keys

API key management (create / list / revoke under an organization), the key "whoami" endpoint, and how `hk-...` keys authenticate requests against the portal API (EU `https://portal.api.eu.hcompany.ai`, US `https://portal.production.hcompany.ai`, routes under `/api`). The browser UI for managing keys is on the separate product frontend: `https://platform.hcompany.ai/settings/api-keys`.

**Sources:** `domains/api_key/controller.py`, `domains/api_key/dtos.py`, `domains/services/api_key.py`, `core/dependencies.py` (`require_api_key`), `domains/key_validator/` + `domains/api_key_validator/` (Lambda authorizers).

## Contents

- [Endpoints overview](#endpoints-overview)
- [Create an API key](#create-an-api-key)
- [List API keys](#list-api-keys)
- [Revoke (delete) an API key](#revoke-delete-an-api-key)
- [Whoami: GET /api/api-keys/me](#whoami-get-apiapi-keysme)
- [How API keys authenticate requests](#how-api-keys-authenticate-requests)
- [Validator domains (internal, no HTTP routes)](#validator-domains-internal-no-http-routes)
- [Errors](#errors)
- [Lifecycle & gotchas](#lifecycle--gotchas)

## Endpoints overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/organizations/{org_id}/keys/` | Session cookie + org access | Create key (returns full `hk-...` value, once) |
| GET | `/api/organizations/{org_id}/keys/` | Session cookie + org access | List all keys in the org (masked) |
| DELETE | `/api/organizations/{org_id}/keys/{key_id}` | Session cookie + org access | Revoke a key (owner only) |
| GET | `/api/api-keys/me` | The API key itself | Whoami for a key + its organization |

The management router is mounted in `organization/controller.py` under `/organizations`, with router-level dependencies `get_user_from_cookie` + `require_org_access` — so every management call requires a logged-in platform user who is a member of `{org_id}`. These endpoints are **not** callable with an API key; only `/api/api-keys/me` is.

## Create an API key

`POST /api/organizations/{org_id}/keys/` → `201 Created`

Request body (`ApiKeyCreateInput`):

```json
{
  "name": "ci-deploy-key",
  "expiry_date": "2026-12-31"
}
```

- `name` (string, required) — unique per organization (DB constraint on `(organization, name)`).
- `expiry_date` (date `YYYY-MM-DD`, optional) — omit or `null` for a non-expiring key.

Response (`ApiKeyCreateOutput`):

```json
{
  "id": "5f1c9c5e-2a7b-4d2e-9c1a-8e3f6b2d4a01",
  "key": "hk-3f9a1c0d7e5b2a8f4c6d1e0b9a7f3c2d5e8b1a4f6c9d0e2b",
  "expires_at": "2026-12-31",
  "created_at": "2026-06-10T14:32:11.123456Z",
  "name": "ci-deploy-key"
}
```

`key` is the full plaintext key (`hk-` + 48 hex chars, from `secrets.token_hex(24)`). **This is the only response, anywhere, that ever contains the full key.** Only the SHA256 hash is stored; the plaintext cannot be retrieved later. The key is owned by the calling user (`require_db_user`) and scoped to `{org_id}`.

Duplicate name in the same org → `400` `api_key_name_already_exists`.

## List API keys

`GET /api/organizations/{org_id}/keys/` → `200 OK`

No query parameters. Returns **all** keys in the organization (every member's keys, not just the caller's). Response is a JSON array of `ApiKeyListOutput`:

```json
[
  {
    "id": "5f1c9c5e-2a7b-4d2e-9c1a-8e3f6b2d4a01",
    "key_display": "hk-3...e2b",
    "expires_at": "2026-12-31",
    "created_at": "2026-06-10T14:32:11.123456Z",
    "name": "ci-deploy-key",
    "owner_id": "0b2d4a01-8e3f-6b2d-4a01-5f1c9c5e2a7b",
    "owner_email": "mathieudiaz@hcompany.ai"
  }
]
```

- `key_display` is a mask built at creation time: first 4 + `...` + last 4 chars of the raw key (e.g. `hk-3...e2b`). The full key is never returned.
- Expired keys still appear in the list (no filtering by expiry here).

## Revoke (delete) an API key

`DELETE /api/organizations/{org_id}/keys/{key_id}` → `204 No Content` (empty body)

- Hard-deletes the key row; the key stops authenticating immediately.
- **Only the key's owner can delete it** — even an org member who can see the key in the list gets `403` `api_key_unauthorized` if they don't own it.
- The key must belong to `{org_id}`; otherwise `404` `api_key_not_found`.

## Whoami: GET /api/api-keys/me

`GET /api/api-keys/me` → `200 OK`

Authenticated by the API key itself (no cookie/session needed) — pass `Authorization: Bearer hk-...` or `x-api-key: hk-...`. Use it to discover which key/org a credential belongs to.

```bash
# EU host shown; US: https://portal.production.hcompany.ai
curl https://portal.api.eu.hcompany.ai/api/api-keys/me \
  -H "Authorization: Bearer hk-3f9a1c0d...0e2b"
```

Response (`ApiKeyMeOutput`, with nested `OrganizationOut`):

```json
{
  "id": "5f1c9c5e-2a7b-4d2e-9c1a-8e3f6b2d4a01",
  "name": "ci-deploy-key",
  "key_display": "hk-3...e2b",
  "expires_at": "2026-12-31",
  "created_at": "2026-06-10T14:32:11.123456Z",
  "organization": {
    "id": "9c1a8e3f-6b2d-4a01-5f1c-9c5e2a7b4d2e",
    "name": "H Company",
    "created_at": "2025-01-15T09:00:00Z",
    "updated_at": "2026-05-01T12:00:00Z",
    "is_active": true
  }
}
```

Missing key → `401` "Missing API key." Unknown or expired key → `401` "Invalid or expired API key."

## How API keys authenticate requests

Implemented by `require_api_key` in `core/dependencies.py`:

1. **Header extraction** (`_extract_api_key`), in priority order:
   - `Authorization: Bearer hk-...` (case-insensitive `bearer ` prefix, value trimmed)
   - `x-api-key: hk-...` (fallback if no usable Authorization header)
2. **Lookup by hash**: the raw key is SHA256-hashed (`hashlib.sha256(key.encode()).hexdigest()`) and matched against the stored hash — plaintext keys never touch the database.
3. **Expiry check**: a key with `expires_at <= today` (date granularity) is rejected as expired. Expiry is enforced at auth time only; expired keys remain in the DB and in list output until deleted.
4. On success the request gets an `ApiKeyContext { user_id, org_id, api_key_id }` (key owner + owning org). All failures return `401` with title `unauthorized`.

## Validator domains (internal, no HTTP routes)

`domains/key_validator/` and `domains/api_key_validator/` expose **no FastAPI routes** — they are AWS Lambda **API Gateway custom authorizers** used by other H services (Agent Platform, Tester-H, Agent Environments, H Platform). You never call them over `/api`; API Gateway invokes them per request.

- **`key_validator`** (current): accepts API Gateway `REQUEST` authorizer events or `CUSTOM` events (`KeyValidationRequest`: `{key, auth_type, application_id, resource_name?, request_id?, resource?, type: "CUSTOM"}`). Handles **both** auth types — an `hk-...` API key or a platform JWT (from `Authorization` header, or the access-token cookie). It validates application access, applies Redis-backed tier rate limits (the four first-party app IDs are exempt from tier limits and only abuse-capped), and returns an IAM Allow/Deny policy whose `context` carries `orgId`, `userId`, `email`, `role`, `orgRole`, `api_key_hashed`, `rate_limit_*`, etc. for downstream services.
- **`api_key_validator`** (older variant): same authorizer pattern but API-key-only, with tier rate limiting.

Keys are validated by the same SHA256 hash lookup (`ApiKeyService.hash_key`), so revoking a key on the platform immediately cuts off access to all H services fronted by these authorizers.

## Errors

| Status | title | When |
|---|---|---|
| 400 | `api_key_name_already_exists` | Create with a name already used in the org |
| 400 | `organization_not_found` | `{org_id}` doesn't exist (from `require_org_access`) |
| 401 | `unauthorized` | Missing/invalid/expired API key (`/api-keys/me`), or no session cookie |
| 401 | `api_key_expired` | Key past `expires_at` |
| 403 | `permission_denied` | Caller is not a member of `{org_id}` |
| 403 | `api_key_unauthorized` | Deleting a key you don't own |
| 404 | `api_key_not_found` | Key id not found in `{org_id}` |

Error body shape: `{"detail": "...", "title": "..."}`.

## Lifecycle & gotchas

- **The full key appears exactly once** — in the `key` field of the create response. Capture it immediately; afterwards only `key_display` (`hk-3...e2b`) is available. Losing it means creating a new key.
- **Deterministic naming + revoke-by-name**: names are unique per org, so use a stable, deterministic name per purpose (e.g. `ci-{repo}`, `hai-agent-demos-local`). To rotate without orphans: GET the list, find entries with your name, DELETE them by `id`, then POST a fresh key with the same name. Creating first and deleting later fails with `api_key_name_already_exists`.
- **Org access is mandatory**: all management routes sit behind `require_org_access` — a valid session for a user who is a member of `{org_id}`. API keys cannot manage API keys.
- **Owner-only deletion**: listing is org-wide, deletion is owner-only. Cleanup scripts must run as the user who created the keys.
- **Expiry is date-based and lazy**: a key expires at the start of its `expires_at` date and is rejected at auth time, but stays visible in list output until explicitly deleted.
- **Trailing slash matters**: create/list routes are defined at `"/"` under the `/{org_id}/keys` prefix — use `/api/organizations/{org_id}/keys/` to avoid redirects.
- **Revocation is global**: because every H service validates via the same hashed-key lookup (Lambda authorizers above), deleting a key revokes it platform-wide immediately.
