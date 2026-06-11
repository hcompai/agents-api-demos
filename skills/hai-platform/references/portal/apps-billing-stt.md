# Applications, Billing, STT & Guest

Endpoints for application catalog CRUD, Stripe credit billing, and realtime speech-to-text token minting on the portal API (EU `https://portal.api.eu.hcompany.ai`, US `https://portal.production.hcompany.ai`, routes under `/api`), plus shared API conventions (errors, health, environments, admin surface).

**Sources:** `domains/application/{controller,dtos}.py`, `domains/billing/{controller,dtos,exceptions}.py`, `domains/stt/{controller,dtos,exceptions}.py`, `domains/guest/controller.py`, `core/{exceptions,exception_handlers,middleware,health,routes,dependencies}.py`, `django/settings.py`, `app.py`, frontend `src/lib/portal/portal-client.ts`.

## Contents

- [Endpoints overview](#endpoints-overview)
- [Applications](#applications)
- [Billing](#billing)
- [Speech-to-text (STT)](#speech-to-text-stt)
- [Guest domain (no HTTP routes)](#guest-domain-no-http-routes)
- [Conventions](#conventions)
  - [Error response shape](#error-response-shape)
  - [Health check](#health-check)
  - [Rate limiting](#rate-limiting)
  - [CORS](#cors)
  - [Environments & base URLs](#environments--base-urls)
  - [Admin / internal routers](#admin--internal-routers)

## Endpoints overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/applications/` | Session cookie / Bearer JWT | List applications the user can access |
| POST | `/api/applications/` | Cookie + platform `ADMIN` role | Create an application |
| GET | `/api/applications/{application_id}` | Session cookie / Bearer JWT | Get one application |
| DELETE | `/api/applications/{application_id}` | Cookie + platform `ADMIN` role | Delete an application (204) |
| POST | `/api/billing/checkout-sessions` | Cookie, org selected | Create Stripe checkout session (201) |
| POST | `/api/billing/checkout-sessions/{session_id}/apply` | Cookie, org selected | Apply credits from a paid session |
| GET | `/api/billing/balance` | Cookie, org selected | Current org credit balance |
| GET | `/api/billing/transactions` | Cookie, org selected | Paginated credit ledger |
| POST | `/api/stt/token` | API key (`hk-...`) | Mint short-lived realtime STT token |

"Cookie" auth = `get_user_from_cookie`: an access-token JWT read from the environment-prefixed cookie (`access_token`, `staging_access_token`, `dev_access_token`, `sandbox_access_token`) or an `Authorization: Bearer <jwt>` header. Invalid/expired tokens and revoked sessions yield 401 `application/problem+json` (`title`: `token_expired`, `invalid_token`, or `invalid_session`).

## Applications

Router prefix `/applications`, router-level `Depends(get_user_from_cookie)` — every route requires a logged-in user. Write operations additionally require `role_guard([UserRole.ADMIN])` (platform-level admin role on the JWT; superadmins always pass; others get 403).

### GET /api/applications/

Lists applications visible to the caller. Uses the `applications` IDs in the JWT `access` claim when present; otherwise falls back to computing the user's app grants server-side. On lookup failure returns `[]` (not an error). Response: `list[ApplicationOut]`.

```json
[
  {
    "name": "Agent Platform",
    "description": "H agent platform",
    "url": "https://agent-computer-use.hcompany.ai",
    "is_active": true,
    "grant_by_default": false,
    "id": "0c4f9f9e-2c4e-4f7a-9e1a-1c2d3e4f5a6b",
    "released_at": "2026-01-15T10:00:00Z"
  }
]
```

### POST /api/applications/ (ADMIN)

Body `ApplicationPayload`:

```json
{
  "name": "My App",
  "description": "What it does",
  "url": "https://myapp.hcompany.ai",
  "is_active": true,
  "grant_by_default": false
}
```

- `url` is optional (`HttpUrl | null`); an empty string is coerced to `null`.
- `is_active` defaults `true`, `grant_by_default` defaults `false`.
- Returns `ApplicationOut` (payload fields + `id` UUID + `released_at` datetime). 200 on success, 403 for non-admins, 422 on validation errors.

### GET /api/applications/{application_id}

Returns the application or **404** `{"detail": "Application not found"}` (plain FastAPI `HTTPException`, not the problem-detail shape). No response_model declared — returns the service object serialized.

### DELETE /api/applications/{application_id} (ADMIN)

Returns **204 No Content**. 403 for non-admins.

## Billing

Router prefix `/billing`, all routes cookie-authenticated. Every endpoint first requires an organization on the JWT: if `org_id` is missing → **400** `{"title": "no_organization_selected", "status": 400, "detail": "No organization selected. Please select an organization."}`. Credits are managed as a Stripe customer balance per org billing account.

### POST /api/billing/checkout-sessions → 201

Body `CheckoutSessionCreatePayload`:

```json
{ "amount_cents": 5000 }
```

`amount_cents` must be 100–1,000,000 ($1 min, $10,000 max; 422 outside the range). Creates (or reuses) the org's billing account and a Stripe Checkout session. Response `CheckoutSessionOut`:

```json
{ "session_id": "cs_test_a1B2...", "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1B2..." }
```

Errors: 502 `Checkout Session Creation Failed`, 502 `Billing Service Error` (Stripe API failure), 500 `Internal Server Error` (catch-all).

### POST /api/billing/checkout-sessions/{session_id}/apply

Credits a *paid* checkout session to the org balance (idempotent), also sweeps any other unapplied paid sessions, then returns the fresh balance. Response `ApplySessionOut`:

```json
{ "applied": true, "balance_cents": 5000, "balance_usd": "$50.00" }
```

`applied: false` means the session had already been credited. Errors: 400 `Checkout Session Not Paid`, 403 `Session Ownership Mismatch` (session belongs to another org), 404 `Billing Account Not Found`, 502 `Billing Service Error`, 500 catch-all.

### GET /api/billing/balance

Response `BalanceOut`. If the org has no billing account yet, returns zeros instead of 404:

```json
{ "balance_cents": 0, "balance_usd": "$0.00" }
```

Also opportunistically applies any unapplied paid sessions before reading the balance. Errors: 404 `Billing Account Not Found` (race), 500 catch-all.

### GET /api/billing/transactions

Query params: `limit` (1–100, default 10), `starting_after` (transaction id cursor, optional). Response `TransactionListOut` (newest first); no billing account → `{"transactions": [], "has_more": false}`.

```json
{
  "transactions": [
    {
      "id": "cbtxn_1Q...",
      "amount_cents": 5000,
      "balance_cents": 5000,
      "description": "Credit purchase",
      "metadata": {"checkout_session_id": "cs_..."},
      "created_at": "2026-06-01T12:00:00Z",
      "receipt_url": "https://pay.stripe.com/receipts/...",
      "invoice_url": null
    }
  ],
  "has_more": false
}
```

`amount_cents` positive = credit, negative = debit; `balance_cents` is the running balance after the transaction. `description`, `metadata`, `receipt_url`, `invoice_url` are nullable.

## Speech-to-text (STT)

Router prefix `/stt`. **Auth differs from the rest of this file:** authenticated with a portal API key (`hk-...`) via `require_api_key`, sent as `Authorization: Bearer hk-...` or `x-api-key: hk-...`. No session cookie involved. Missing key → 401 `unauthorized` / "Missing API key."; invalid or expired key → 401 `unauthorized` / "Invalid or expired API key."

### POST /api/stt/token → 200

No request body. Mints a short-lived ElevenLabs realtime STT token. Response `SttTokenOut`:

```json
{
  "token": "xi_rt_...",
  "expires_at": "2026-06-10T12:15:00Z",
  "provider": "elevenlabs"
}
```

Token TTL ~15 minutes (`ELEVENLABS_TOKEN_TTL_SECONDS = 900`), single-use; clients should connect to the provider immediately and never cache it.

Error cases (problem-detail bodies):

| Status | `title` | Meaning |
|---|---|---|
| 429 | `stt_mint_rate_limited` | Rate limit hit; includes `Retry-After: <seconds>` header (always ≥ 1) |
| 502 | `stt_unavailable` | ElevenLabs returned non-2xx (upstream status logged, not leaked) |
| 500 | `stt_token_mint_failed` | Token missing/unparseable from provider response |

Mint rate limits (Redis sliding windows, defaults from `SttSettings`, all env-overridable):

1. Per API key burst: 10 / 60 s — fails *open* on limiter errors.
2. Per org steady-state: 500 / hour — fails *open*.
3. Per org monthly cap: 20,000 / 30 days — fails *closed* by default (`STT_MINT_MONTHLY_CAP_FAIL_CLOSED=true`), so a Redis outage cannot bypass the vendor-spend ceiling; in that failure mode `Retry-After` is a best-effort 60 s.

`STT_MINT_RATE_LIMIT_ENABLED=false` disables all three.

## Guest domain (no HTTP routes)

`domains/guest/controller.py` exposes **no FastAPI routes**. `GuestAuthorizerController` is a branch of the AWS API Gateway REQUEST Lambda authorizer: for configured guest resources (currently only paths matching the agent-computer-use resource marker), when a request has *no* `Authorization` header and *no* Portal access-token cookie, it returns an IAM `Allow` policy with `principalId: "anonymous"` and context `{anonymous: "true", auth_type: "anonymous", role: "anonymous", orgRole: "anonymous"}` so the downstream API can decide which paths actually need auth. Any credentialed request falls through to full key/JWT validation. Nothing here is callable on the portal API hosts directly.

## Conventions

### Error response shape

`APIException` (subclass of `HTTPException`) is rendered by a global handler as RFC-7807-style problem details with `Content-Type: application/problem+json`:

```json
{ "title": "stt_mint_rate_limited", "status": 429, "detail": "Too many speech-to-text token requests. Please retry later." }
```

- Fields: `title` (machine-ish error code or human title — naming is inconsistent across domains), `status` (int), `detail` (nullable string).
- Exception-defined headers (e.g. `Retry-After`) are merged into the response.
- `DEFAULT_ERROR_RESPONSES` registers a 500 `ProblemDetail` on every route; `responses_for(...)` adds per-exception OpenAPI entries.
- Auth failures map to 401 problem details with titles `token_expired`, `invalid_token`, `invalid_session` (plus `WWW-Authenticate: Bearer ...` for invalid sessions). Redis connection failures → 503 `service_unavailable`.
- Caveat: a few handlers raise plain `HTTPException` (e.g. application 404), which FastAPI renders as `{"detail": "..."}` JSON, not problem+json. Pydantic validation errors are standard FastAPI 422s.

### Health check

`GET /health_check` (no `/api` prefix, unauthenticated). Verifies Postgres (`SELECT 1`) and Redis (`PING`):

```json
{ "db": "ok", "redis": "ok", "status": "healthy" }
```

On failure: 500 with `{"status": "unhealthy", "error": "..."}` (and a per-check `"ko"` value when only one dependency is down).

### Rate limiting

There is **no global rate-limit middleware** on the FastAPI app — `core/middleware.py` only installs CORS. Rate limiting exists at two layers: (1) the STT mint limits described above (Redis sliding windows, per-key / per-org / monthly), and (2) the `rate_limit_tier` domain, which defines org/app/resource tiers enforced at the AWS API Gateway / key-validator layer for API-key traffic, managed via admin-engine endpoints (internal app only).

### CORS

`CORSMiddleware` with origins from `CORS_ALLOWED_ORIGINS` env (comma-separated; default `http://localhost:3000`), regex `CORS_ALLOW_ORIGIN_REGEX` (default localhost-only), credentials allowed, methods `GET POST PUT PATCH DELETE OPTIONS`, preflight cached 1 h.

### Environments & base URLs

- **Portal API hosts (verified live):** production US `https://portal.production.hcompany.ai` (unauthenticated browser requests 302 to the Cognito flow on `oauth.hcompany.ai`), production EU `https://portal.api.eu.hcompany.ai` (302 to `sso.hcompany.ai`), staging `https://portal.api.eu.staging.sandboxh.ai`. All portal routes in these docs live under these hosts + `/api`.
- **Portal frontends** (cookie domain, login pages): `https://portal.hcompany.ai` (US) and `https://portal.eu.hcompany.ai` (EU).
- **`https://platform.hcompany.ai` is NOT the portal API** — it is the separate Next.js product frontend (`platform-frontend`). It hosts the API-keys management UI at `/settings/api-keys` and a server-side proxy `/api/portal/[...path]` that forwards (cookies only) to the portal API. Calling `platform.hcompany.ai/api/auth/*` directly returns the HTML app shell, not JSON.
- **Environment switch:** `ENVIRONMENT` env var ∈ `DEV` (default), `SANDBOX`, `STAGING`, `PRODUCTION`, `test`. It drives cookie naming (`{env}_access_token` prefix except production), `DEBUG` (DEV only), and `COOKIE_SECURE` (true for SANDBOX/STAGING/PRODUCTION). `COOKIE_DOMAIN` env sets the cookie scope (e.g. `.hcompany.ai` in production).
- **Local dev:** backend `http://localhost:8000` (public app), frontend `http://localhost:3000`. With `ENVIRONMENT=DEV` the Django admin panel is additionally mounted at `/web`.

### Admin / internal routers

Admin and admin-engine routers (organizations, users, memberships, invitations, applications, app access/resources, API keys, rate-limit tiers, internal user/org lookup, plus `/docs`) exist but are **not** part of the public API. There is no `ENABLE_*` env var: `app.py` builds two ASGI apps from the same codebase — `create_app(is_internal=True)` → `portal_h.asgi:internal_app` (all public routes + admin routers + OpenAPI docs) and `create_app(is_internal=False)` → `portal_h.asgi:public_app` (public routes only, docs/openapi disabled). The deployment-time gate is which ASGI target uvicorn serves: `deploy.sh` runs `public_app` on port 8000 and `internal_app` on port 9000, and only the public app is exposed at the public portal API hosts (`portal.production.hcompany.ai` / `portal.api.eu.hcompany.ai`); admin routes 404 on the public app. The only env-var-gated mount is the Django admin (`ENVIRONMENT=DEV` mounts it at `/web`).
