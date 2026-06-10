# Organizations & Invitations API

Public endpoints for organizations, memberships, and invitations in the portal backend (portal API hosts: EU `https://portal.api.eu.hcompany.ai`, US `https://portal.production.hcompany.ai`, staging `https://portal.api.eu.staging.sandboxh.ai`; all routes under `/api`).

Source: `backend/portal_h/src/portal_h/domains/organization/` (`controller.py`, `invitation_controller.py`, `dtos.py`, `guard.py`, `exceptions.py`) and `domains/services/organization.py`.

## Table of contents

- [Authentication](#authentication)
- [Guards and role checks](#guards-and-role-checks)
- [Organizations](#organizations)
  - [GET /api/organizations/](#get-apiorganizations)
  - [GET /api/organizations/owned](#get-apiorganizationsowned)
  - [GET /api/organizations/{org_id}](#get-apiorganizationsorg_id)
- [Membership management](#membership-management)
  - [DELETE /api/organizations/{org_id}/membership/{membership_id}](#delete-apiorganizationsorg_idmembershipmembership_id)
- [Organization invitations (owner side)](#organization-invitations-owner-side)
  - [POST /api/organizations/{org_id}/invitations](#post-apiorganizationsorg_idinvitations)
  - [GET /api/organizations/{org_id}/invitations](#get-apiorganizationsorg_idinvitations)
- [My invitations (invitee side)](#my-invitations-invitee-side)
  - [GET /api/invitations/me](#get-apiinvitationsme)
  - [POST /api/invitations/{invitation_id}/accept](#post-apiinvitationsinvitation_idaccept)
  - [POST /api/invitations/{invitation_id}/decline](#post-apiinvitationsinvitation_iddecline)
- [Temporal sub-router](#temporal-sub-router)
- [API key sub-router](#api-key-sub-router)
- [Current user (/users/me equivalent)](#current-user-usersme-equivalent)
- [DTO reference](#dto-reference)
- [Error model](#error-model)

## Authentication

Every endpoint here uses the **hybrid auth dependency** `get_user_from_cookie` (`core/dependencies.py`). Despite the name, it accepts **either**:

1. **Cookie** (preferred for browsers): `access_token` cookie. Name is environment-prefixed: `access_token` (prod), `staging_access_token`, `dev_access_token`, `sandbox_access_token`.
2. **Bearer token** (fallback for API clients): `Authorization: Bearer <access_token>`.

Cookie wins if both are present. Tokens are checked against a revocation cache (`AccessTokenCache`); a revoked token gets `401` with title `token_revoked`. Missing credentials → `401` `unauthorized`. The decoded token is an `AccessTokenDTO` whose `sub` (Cognito sub) identifies the user.

The whole organizations router declares `dependencies=[Depends(get_user_from_cookie)]`, so **all** routes below require auth.

## Guards and role checks

- **`require_org_access`** (`organization/guard.py`): router-level dependency used by sub-routers (e.g. temporal). Resolves `org_id` from the path and calls `OrganizationService.get_organization(org_id, user.sub)`. Raises `400` (title `organization_not_found`) if the org doesn't exist and `403` (title `permission_denied`) if the user isn't a member. Note the 400-vs-404 quirk: the guard maps a missing org to **400**, while the main controller maps it to **404**.
- **Membership check**: `get_organization` denies access unless the user has a `Membership` in the org (any role).
- **Owner-only checks** are enforced in the service layer (not the guard): `delete_membership`, `create_invitation`, and `list_organization_invitations` require the caller's membership role to be `owner` (`OrganizationRole.OWNER`), otherwise `PermissionDenied` → `403`.
- Membership roles are `owner` and `user`.

## Organizations

There are **no public create/update/delete organization endpoints**. Organizations are created automatically (default org on signup via `create_default_organization`) or through admin-only routers (`admin_controller.py`, mounted only when admin routes are enabled). `OrganizationCreatePayload` / `OrganizationUpdatePayload` DTOs exist but are used by the service/admin layer only.

### GET /api/organizations/

List all organizations the current user is a member of (any role).

- **Auth**: cookie or Bearer. **Guard**: authenticated user only.
- **Response** `200`: `list[OrganizationOut]`

```json
[
  {
    "id": "0c4f9a2e-1d3b-4f6a-9e8c-2a7b5d4c3f10",
    "name": "Acme Corp",
    "created_at": "2026-01-15T10:30:00Z",
    "updated_at": "2026-02-01T08:00:00Z",
    "is_active": true
  }
]
```

### GET /api/organizations/owned

List only the organizations where the current user's membership role is `owner`.

- **Auth**: cookie or Bearer.
- **Response** `200`: `list[OrganizationOut]` (same shape as above).

### GET /api/organizations/{org_id}

Get one organization with its member list.

- **Auth**: cookie or Bearer. **Guard**: caller must be a member (any role).
- **Response** `200`: `OrganizationWithMembersOut`

```json
{
  "id": "0c4f9a2e-1d3b-4f6a-9e8c-2a7b5d4c3f10",
  "name": "Acme Corp",
  "created_at": "2026-01-15T10:30:00Z",
  "updated_at": "2026-02-01T08:00:00Z",
  "is_active": true,
  "members": [
    {
      "id": "7e2d1c0b-9a8f-4e6d-b5c4-3a2b1c0d9e8f",
      "role": "owner",
      "joined_at": "2026-01-15T10:30:00Z",
      "user_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
      "user_email": "alice@example.com"
    }
  ]
}
```

- **Errors**: `404` Organization Not Found; `403` Permission Denied (not a member); `401` unauthenticated.

## Membership management

There is no public endpoint to change a member's role; role changes go through admin routes. The only public member operation is removal.

### DELETE /api/organizations/{org_id}/membership/{membership_id}

Remove a member from an organization. **Owners only.** `membership_id` is the `Membership` row id (the `members[].id` field from `GET /api/organizations/{org_id}`), not the user id.

- **Auth**: cookie or Bearer. **Guard**: caller must hold an `owner` membership in the org (service-level check).
- **Response** `200`: updated `OrganizationWithMembersOut` (same shape as above, with the member removed).
- **Errors**: `404` Organization Not Found; `403` Permission Denied (`"Only organization owners can remove members"`); `400` Membership Not Found; `401` unauthenticated.

## Organization invitations (owner side)

Invitations are how members join an org. There is **no public revoke endpoint** — revoking a pending invitation is admin-only (`admin_invitations_resource.py`). Accepted/declined state is set by the invitee via `/api/invitations/...`.

### POST /api/organizations/{org_id}/invitations

Create an invitation and send the invitee an email (via SES) containing the invitation id and expiry. **Owners only.**

- **Auth**: cookie or Bearer. **Guard**: owner membership required (service-level check).
- **Request body** (`InvitationCreatePayload`):

```json
{
  "email": "bob@example.com",
  "role": "user"
}
```

`role` defaults to `"user"`; valid values are `"owner"` and `"user"` (anything else → `400 Invalid Role`).

- **Response** `201`: `InvitationOut`

```json
{
  "id": "f0e1d2c3-b4a5-4968-8776-655443322110",
  "email": "bob@example.com",
  "role": "user",
  "organization_name": "Acme Corp",
  "invited_by": "alice@example.com",
  "status": "pending",
  "invited_at": "2026-06-10T09:00:00Z",
  "expires_at": "2026-06-17T09:00:00Z",
  "responded_at": null
}
```

- **Errors**:
  - `404` Organization Not Found
  - `403` Permission Denied (`"Only organization owners can send invitations"`)
  - `400` Bad Request — invalid role, `"User already has a pending invitation"` (InvitationAlreadyExists), or `"User is already a member of this organization"` (UserAlreadyMember)
  - `401` unauthenticated

### GET /api/organizations/{org_id}/invitations

List all invitations for an organization (any status). **Owners only.**

- **Auth**: cookie or Bearer. **Guard**: owner membership required.
- **Response** `200`: `list[InvitationOut]` (same shape as above).
- **Errors**: `404` Organization Not Found; `403` Permission Denied (`"Only organization owners can view invitations"`); `401`.

## My invitations (invitee side)

Separate router (`invitation_controller.py`) with prefix `/invitations`, mounted directly under `/api` (not under `/organizations`). Auth via the same hybrid dependency per-endpoint.

### GET /api/invitations/me

List the current user's **pending** invitations (matched by the user's email).

- **Auth**: cookie or Bearer.
- **Response** `200`: `list[InvitationOut]`.

### POST /api/invitations/{invitation_id}/accept

Accept an invitation; creates the membership with the invited role. No request body.

- **Auth**: cookie or Bearer. **Guard**: invitation email must match the caller's email.
- **Response** `200`: `InvitationResponseOut`

```json
{
  "invitation_id": "f0e1d2c3-b4a5-4968-8776-655443322110",
  "status": "accepted",
  "message": "Invitation accepted",
  "organization_name": "Acme Corp",
  "membership_id": "7e2d1c0b-9a8f-4e6d-b5c4-3a2b1c0d9e8f"
}
```

- **Errors** (raised as `APIException` subclasses from `organization/exceptions.py`, handled globally):
  - `404` Invitation Not Found / User Does Not Exist
  - `403` Permission Denied (`"You can only accept invitations sent to you"`)
  - `409` Invitation Already Responded
  - `410` Invitation Expired
  - `400` User Already Member of another Organization (accepting while already in a non-default org)
  - `401` unauthenticated

### POST /api/invitations/{invitation_id}/decline

Decline an invitation. No request body.

- **Auth**: cookie or Bearer. **Guard**: invitation email must match the caller's email.
- **Response** `200`: `InvitationResponseOut` with `"status": "declined"` (`organization_name`/`membership_id` may be `null`).
- **Errors**: `404` Invitation Not Found; `403` Permission Denied (`"You can only decline invitations sent to you"`); `409` Invitation Already Responded; `401`.

## Temporal sub-router

`domains/temporal/controller.py`, included by the organizations router. Prefix `/{org_id}/temporal` → mounted at **`/api/organizations/{org_id}/temporal`** (verified: org router prefix `/organizations` + sub-router prefix `/{org_id}/temporal`, all under the `/api` base router). Router-level guards: `get_user_from_cookie` **and** `require_org_access` (member of the org, any role).

### POST /api/organizations/{org_id}/temporal/worker-token

Issue a namespace-scoped Temporal **worker JWT**. The token grants `RoleWorker` for the single namespace `namespace-{sanitized_org_id}-001` (sanitization: lowercase, strip everything except `a-z0-9-`) — it can poll task queues and respond to tasks, but cannot start workflows, list executions, or touch other namespaces. TTL: **90 days**. Token claims include `sub: "worker:<namespace>"`, `type: "worker"`, `org_id`, `namespace`, `aud: "temporal"`, and `issued_by` (the requesting user's sub). No request body.

- **Response** `201` (`WorkerTokenOutput`):

```json
{ "token": "eyJhbGciOi..." }
```

- **Errors**: `400` organization_not_found (guard quirk); `403` permission_denied; `401`.

## API key sub-router

Also included by the organizations router: `domains/api_key/controller.py` with prefix `/{org_id}/keys`, i.e. endpoints live under **`/api/organizations/{org_id}/keys/`** (POST `/` create, GET `/` list, DELETE `/{key_id}`). There is also a standalone `GET /api/api-keys/me`. Documented separately — see the api-keys reference.

## Current user (/users/me equivalent)

The `user` domain has **no public controllers** (only admin/internal: `admin_resource.py`, `admin_lookup_controller.py`). The current-user endpoint lives in the auth domain:

### GET /api/auth/me

Comprehensive current-user info (`CurrentUserResponse`): embedded `user` profile (`id`, `cognito_sub`, `email`, `username`, `role`, `created_at`, `updated_at`, `is_active`, `email_verified`, `last_login`), plus `authenticated`, `authentication_method` (`"cookie"` or `"bearer"`), `token_expires_at`, accessible `applications` list, `total_application_count`, session info, org context, and `mfa_enabled`. Auth: cookie or Bearer. `401` if the token's user no longer exists in the DB.

## DTO reference

`organization/dtos.py`:

| DTO | Fields |
|---|---|
| `OrganizationOut` | `id: UUID`, `name: str`, `created_at`, `updated_at`, `is_active: bool` |
| `OrganizationWithMembersOut` | `OrganizationOut` fields + `members: list[MembershipOut]` |
| `MembershipOut` | `id: UUID` (membership id), `role: str`, `joined_at`, `user_id: UUID`, `user_email: str` |
| `InvitationCreatePayload` | `email: str`, `role: str = "user"` |
| `InvitationOut` | `id`, `email`, `role`, `organization_name`, `invited_by`, `status`, `invited_at`, `expires_at`, `responded_at: datetime \| null` |
| `InvitationResponseOut` | `invitation_id`, `status`, `message`, `organization_name: str \| null`, `membership_id: UUID \| null` |
| `OrganizationCreatePayload` | `name: str` (admin/service use only) |
| `OrganizationUpdatePayload` | `name?: str`, `is_active?: bool` (admin/service use only) |
| `WorkerTokenOutput` (temporal) | `token: str` |

## Error model

Errors are `APIException` (RFC-7807-style) with `status_code`, `title`, `detail`. Domain exception → HTTP mapping (`organization/exceptions.py`):

| Exception | Status |
|---|---|
| `OrganizationNotFound`, `InvitationNotFound`, `UserDoesNotExist` | 404 |
| `PermissionDenied` | 403 |
| `InvalidRole`, `UserAlreadyMember`, `UserAlreadyMemberNonDefaultOrg`, `InvitationAlreadyExists`, `OrganizationAlreadyExists`, `MembershipNotFound` | 400 |
| `InvitationAlreadyResponded` | 409 |
| `InvitationExpired` | 410 |
| Missing/invalid/revoked token | 401 |

Remember: `require_org_access` (sub-routers like temporal) maps a missing org to **400**, while the main org controller endpoints return **404**.
