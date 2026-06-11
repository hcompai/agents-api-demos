# Auth API Reference (portal)

All authentication endpoints for the portal backend (Cognito-backed, custom JWT sessions). Router prefix `/auth`, mounted under `/api` → all paths below live on the **portal API hosts**: production US `https://portal.production.hcompany.ai/api/auth/...`, production EU `https://portal.api.eu.hcompany.ai/api/auth/...`, staging `https://portal.api.eu.staging.sandboxh.ai/api/auth/...`. (`https://platform.hcompany.ai` is the separate product frontend and does **not** serve these routes — its `/api/auth/*` returns the HTML app shell.)

## Table of contents

- [Auth model & cookies](#auth-model--cookies)
- [Hybrid auth dependency (cookie OR bearer)](#hybrid-auth-dependency-cookie-or-bearer)
- [OAuth (Google) browser flow](#oauth-google-browser-flow)
- [Desktop/CLI OAuth flow (RFC 8252 + PKCE)](#desktopcli-oauth-flow-rfc-8252--pkce)
- [Email + password login (token endpoint)](#email--password-login)
- [Token refresh](#token-refresh)
- [Logout / revoke](#logout--revoke)
- [Token introspection](#token-introspection)
- [Signup & email verification](#signup--email-verification)
- [Password reset](#password-reset)
- [Sessions](#sessions)
- [Current user (/me)](#current-user-me)
- [MFA (TOTP)](#mfa-totp)

## Auth model & cookies

- Backend mints its own JWT pair (HS256) after authenticating against AWS Cognito.
- **Access token TTL**: 10 min (`JWT_ACCESS_TOKEN_EXPIRES_MINUTES`). **Refresh token TTL**: 1 day default (`JWT_REFRESH_TOKEN_EXPIRES_MINUTES`; 7 days in production).
- Cookies set on login (HttpOnly, `SameSite=Lax`, `Secure` per env, `path=/`):
  - `access_token` (10 min), `refresh_token` (1 day), `session_id` (7 days).
  - **Cookie names are environment-prefixed** via `get_cookie_name()`: production = `access_token`, staging = `staging_access_token`, dev = `dev_access_token`, sandbox = `sandbox_access_token` (same pattern for `refresh_token` / `session_id`).
- **X-SDK-Auth header**: send `X-SDK-Auth: true` on login/refresh/verify/MFA-challenge endpoints to get the tokens **in the JSON response body** (keys are the env-prefixed cookie names, including `session_id`) in addition to cookies. Needed for cross-origin SDK/CLI clients that can't use cookies.
- **No CSRF token mechanism** — protection relies on `SameSite=Lax` HttpOnly cookies and redirect-URL allowlisting (`hcompany.ai` + subdomains; `sandboxh.ai` and `localhost:3000/3001` in non-production; loopback IPs only for the PKCE desktop flow).
- Error format: `APIException` → JSON with `title` (machine-readable) and `detail`.

## Hybrid auth dependency (cookie OR bearer)

`get_user_from_cookie` (core/dependencies.py) guards all "auth required: cookie" endpoints — but despite its name it is **hybrid**:

1. Reads the env-prefixed `access_token` **cookie** first.
2. Falls back to **`Authorization: Bearer <access_token>`** header.

Therefore the `access_token` returned by `POST /api/auth/desktop/exchange` (or SDK-mode login) works as a Bearer token on **every cookie-guarded endpoint** across the API. It also checks a DB revocation list (jti); revoked → `401 token_revoked`. Missing/invalid token → `401 unauthorized`.

(Separately, `require_api_key` accepts `Authorization: Bearer hk-...` or `x-api-key: hk-...` for API-key-guarded routes — different mechanism, not JWT.)

## OAuth (Google) browser flow

Only supported provider: **Google** (via Cognito hosted UI). Any other `provider` → `400 unsupported_provider`.

### GET /api/auth/authorize

OAuth 2.0 authorization endpoint (RFC 6749 §3.1). Auth: none.

Query params:
- `provider` (required) — must be `google`
- `redirect_uri` (optional) — where to land after login; validated against allowlist
- `code_challenge`, `code_challenge_method=S256` (optional) — switches to the desktop PKCE flow (see below)

Returns `302` redirect to the Cognito hosted Google login URL.

### GET /api/auth/callback/{provider}

Cognito redirects here after Google login. Auth: none.

Query params: `code` (required, OAuth authorization code), `state` (either `redirect:<url>` or a desktop-state JWT).

Behavior:
- Exchanges the code with Cognito, registers the user in the local DB if new, creates a default organization for new users.
- Browser flow: issues a token pair + session, sets all three auth cookies, `307` redirect to the validated redirect URL (default: front URL). Session `login_method` = Google OAuth.
- Desktop flow (state is a desktop-state JWT): mints a one-time code and `307`s to the loopback `redirect_uri` with `?code=...` (no cookies, no session yet).
- Federated logins **skip the local TOTP challenge** — Google enforces its own 2FA.
- Errors redirect to `<redirect_url>?error=<type>` with types from `OAuthErrorType`: `google_oauth_failed`, `user_already_exists`, `session_unavailable`, `unexpected_error`, `invalid_code`, `token_exchange_failed`, `user_registration_failed`, `non_oauth_user` (exists but not a Google account).

## Desktop/CLI OAuth flow (RFC 8252 + PKCE)

For native apps/CLIs that can't hold cookies. Step by step:

1. **Client** generates `code_verifier`, computes `code_challenge = BASE64URL(SHA256(code_verifier))` (no padding), and starts a loopback HTTP listener.
2. **Open browser** to:
   ```
   GET /api/auth/authorize?provider=google
       &redirect_uri=http://127.0.0.1:51739/callback
       &code_challenge=<challenge>&code_challenge_method=S256
   ```
   - `redirect_uri` **must be loopback**: `http://127.0.0.1:*` or `http://[::1]:*` (RFC 8252 §7.3). `localhost` is rejected (can resolve off-loopback). Non-loopback + PKCE → `400 invalid_redirect_url`. Method other than `S256` → `400 invalid_pkce_method`.
   - The server packs `redirect_uri` + `code_challenge` into a signed **state JWT valid 5 minutes** (HS256, iss `portal`, aud `portal-desktop-state`) and redirects to Cognito.
3. User completes Google login; Cognito hits `GET /api/auth/callback/google`. The server decodes the state, mints a **one-time opaque code (32 bytes, expires in 60 s)** bound to the user, challenge, and redirect_uri (only SHA-256 of the code is stored), and `307`s to `http://127.0.0.1:51739/callback?code=<code>`.
4. **Client exchanges the code**:
   ```
   POST /api/auth/desktop/exchange
   Content-Type: application/json

   {"code": "<one-time code>", "code_verifier": "<verifier>", "redirect_uri": "http://127.0.0.1:51739/callback"}
   ```
   Response (`DesktopExchangeOutput`):
   ```json
   {"access_token": "eyJ...", "refresh_token": "eyJ...", "session_id": "..."}
   ```
   - Auth: none (the code+verifier are the proof). A real session is created; `login_method` is Google OAuth (desktop codes are only minted by the Google callback).
   - The code is **single-use**: it is deleted before verification (row-locked), so a wrong verifier still burns it. Expired / unknown / reused code, redirect_uri mismatch, or PKCE mismatch → `401 invalid_desktop_code`. Deleted user → `401 user_not_found`.
5. **Use the tokens**: `Authorization: Bearer <access_token>` works on all cookie-guarded endpoints (hybrid dependency). Refresh via `POST /api/auth/token/refresh` with the refresh token + `session_id` in the JSON body and `X-SDK-Auth: true`.

## Email + password login

### POST /api/auth/token

OAuth 2.0 token endpoint (RFC 6749 §3.2) — this is the **login** endpoint. Auth: none.

Body (`LoginInput`): `{"email": "user@example.com", "password": "..."}`
Optional: `X-SDK-Auth: true` header, `?redirect=<url>` query param.

Responses:
- No MFA: `200` `{"success": true, "message": "Login successful"}` + auth cookies (plus tokens in body in SDK mode).
- MFA enabled: `200` `{"success": true, "message": "MFA challenge required", "session": "<cognito session>"}` — **no cookies set**; continue with `POST /api/auth/auth-challenge-response`.

Errors: `400 user_not_found`; `401 not_authorized` (wrong password — counts toward login lockout); `400 mfa_mismatch` (DB flag and Cognito disagree); `400 unexpected_challenge_name`; `503 session_unavailable`; lockout errors from the lockout service after repeated failures.

## Token refresh

### POST /api/auth/token/refresh

Rotate the token pair (RFC 6749 §6). Auth: refresh token (cookie or body) — not the access token.

Inputs (cookie names env-prefixed):
- Browser: `refresh_token` + `session_id` cookies; sends new cookies back.
- SDK/desktop: JSON body `{"refresh_token": "...", "session_id": "..."}` (keys are the env-prefixed cookie names, e.g. `staging_refresh_token` on staging) + `X-SDK-Auth: true` to get the new pair in the response body.
- Optional `X-Selected-Org` header to switch org scope; otherwise the org from the old refresh token is reused.

Response: same shape as login (`{"success": true, "message": "Login successful"}` + cookies / body tokens).

Notable behavior:
- **Refresh coalescing**: concurrent refreshes with the same refresh token are serialized via Redis; followers receive the leader's cached result (prevents multi-tab logout races). Timeout while another refresh runs → `503 refresh_in_progress` (retry).
- The session's refresh token is rotated; reuse of an old refresh token trips reuse detection (session revoked).

Errors: `400 missing_refresh_token`, `400 missing_session_id` (DB-session mode without cookie/body session id), `400 unable_to_refresh_token` (user gone), `401 invalid_token` (expired/invalid refresh token).

## Logout / revoke

### POST /api/auth/revoke

Token revocation (RFC 7009) — logout. Auth: **cookie or bearer**.

Revokes **all sessions for the user** and clears the three auth cookies. Optional `?redirect=<url>`. Response: `204 No Content`.

## Token introspection

### POST /api/auth/introspect

RFC 7662. Auth: none (the token under inspection is the input). Accepts JSON `{"token": "...", "token_type_hint": "..."}` or form-encoded `token=...`.

Active token → `IntrospectionResponse`:
```json
{"active": true, "sub": "<cognito_sub>", "username": "...", "org_id": "...",
 "client_id": "...", "token_type": "Bearer", "exp": 1718000000, "iat": 1717999400,
 "nbf": null, "iss": "...", "aud": "...", "jti": "...", "scope": null}
```
Any invalid/expired/missing token → `{"active": false}` (never an error status).

## Signup & email verification

### POST /api/auth/sign-up

Auth: none. Body (`SignupInput`): `{"email": "a@b.com", "password": "...", "full_name": "..."}`

- New user: registers in Cognito + local DB, creates a default organization, sends a verification email. Returns `SignupOutput`: `{"email": "a@b.com", "message": "An email has been sent to a@b.com. Please check your email"}`.
- **Existing user with correct password: auto-login** (same response/cookies as `/token`, including the MFA-challenge path and `X-SDK-Auth` support). Wrong password → auth error.

### POST /api/auth/verify

Auth: none. Body (`VerifyEmailPayload`): `{"email": "a@b.com", "code": "123456"}`

Confirms the Cognito account and **logs the user in** (cookies set; `X-SDK-Auth: true` supported; `?redirect=` honored). Bad code/email → `400 "Verification failed"`.

### POST /api/auth/resend-confirmation-code

Auth: none. Body: `{"email": "a@b.com"}` (email normalized: trimmed + lowercased).

`200` `{"email": ..., "message": "An email has been sent..."}`. Unknown email → `400 resend_confirmation_failed`. Cognito throttle → `429 too_many_requests`.

## Password reset

### POST /api/auth/forgot-password

Auth: none. Body (`ForgotPassword`): `{"email": "a@b.com"}`. Sends a reset code via Cognito. `200` with `SignupOutput` shape. Unknown email → `400 user_not_found`.

### POST /api/auth/reset-password

Auth: none. Body (`ResetPassword`): `{"email": "a@b.com", "confirmation_code": "123456", "new_password": "..."}`

Confirms the reset with Cognito, **revokes all existing sessions**, then issues a fresh token pair + session (login response, cookies set, `?redirect=` honored).

## Sessions

### GET /api/auth/sessions

Auth: cookie or bearer. Lists the user's sessions. Optional `?page=` and `?page_size=` (DB mode). Response: `list[SessionData]` — session id, user agent, IP, created_at, login_method, etc.

### DELETE /api/auth/sessions/{session_id}

Auth: cookie or bearer. Revokes one session. `204 No Content`. If you delete your **current** session, auth cookies are cleared too. Not found or owned by another user → `400 session_not_found`.

## Current user (/me)

### GET /api/auth/me

Auth: cookie or bearer. Response (`CurrentUserResponse`):

```json
{
  "user": {"id": "uuid", "cognito_sub": "...", "email": "a@b.com", "username": "...",
           "role": "user", "created_at": "...", "updated_at": "...",
           "is_active": true, "email_verified": true, "last_login": null},
  "authenticated": true,
  "authentication_method": "cookie",
  "token_expires_at": "2026-06-10T12:34:56Z",
  "applications": [{"id": "...", "name": "...", "description": null,
                    "is_active": true, "access_granted_at": null}],
  "total_application_count": 1,
  "session": {"session_id": "...", "created_at": "...", "user_agent": "...",
              "ip_address": "...", "login_method": "email"},
  "profile_complete": true,
  "org_id": "...",
  "mfa_enabled": false
}
```

`authentication_method` is `"cookie"` or `"bearer"` (reports which one this request used). `role` ∈ `user | admin | internal | manager | fde_admin`. Stale token for a deleted user → `401 authentication_invalid`.

## MFA (TOTP)

Email/password accounts only (Google logins delegate MFA upstream).

### POST /api/auth/begin-mfa-setup

Auth: cookie or bearer, **plus password re-auth**. Body: `{"password": "..."}`.
Response (`BeginMFASetupMFAResponse`): `{"secret_code": "..."}` (TOTP secret for the QR code).
Errors: `400 invalid_password` (counts toward lockout), `409 mfa_already_enabled`, `400 user_not_found`.

### POST /api/auth/end-mfa-setup

Auth: cookie or bearer. Body (`EndMFASetupMFARequest`): `{"password": "...", "code": "123456"}` (code must be 6 digits → else `400 invalid_code`).

Verifies the TOTP code, **revokes all pre-MFA sessions** (a pre-MFA refresh token would bypass TOTP), enables MFA in Cognito and the DB, then mints a fresh post-MFA session (cookies set). Response: `{"status": "..."}`. If enabling partially fails → `401 mfa_setup_failed_signin_required` or `401 mfa_enabled_signin_required` (user must log in again).

### POST /api/auth/auth-challenge-response

Completes the login MFA challenge. Auth: none (the Cognito `session` from `/token` is the proof).

Body (`EndMFA`): `{"session": "<from /token response>", "email": "a@b.com", "code": "123456"}`

Success → full login response (cookies; `X-SDK-Auth: true` supported; `?redirect=` honored). Bad/expired code → 4xx and counts toward login lockout. `400 mfa_not_enabled` if the user has no MFA.
