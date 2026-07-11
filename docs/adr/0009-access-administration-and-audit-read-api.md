# ADR 0009 — Access-administration API, RBAC auditing, and audit read API

- Status: Accepted
- Date: 2026-06-28

## Context
The RBAC slice (ADR 0007) and the audit slice (ADR 0008) each shipped their
domain, use cases, and gateway/trail, but deliberately deferred three things to
close out Phase 1:

1. an **admin surface** to assign roles and grant per-channel scope (the use
   cases `AssignRole` / `GrantChannelManagement` existed and were tested, but had
   no endpoint);
2. **auditing the RBAC events themselves** (granting access is at least as
   sensitive as changing a channel, yet only channel mutations were audited);
3. a way to **read** the audit trail (ADR 0008 captured it write-only).

This ADR records finishing all three.

## Decision

### A `manage_access` permission, owned by the identity context
Administering *who may do what* is user administration, so the **identity**
context owns the new permission (`domain/identity/permissions.py` →
`manage_access`), mirroring how the channel context owns `manage_channel`. It is
hosted on the identity app's content type (`User.Meta.permissions`, migration
`identity/0003`) so Django can resolve `identity.manage_access`. The access
registry collects it and bundles it into a new `access_admin` role (Django Group,
synced on `post_migrate`). It is a **global-only** permission: administering
access is never object-scoped.

### Access-administration endpoints
Two thin endpoints under `access/`, both gated by `AccessAdminPermission`
(requires the global `manage_access`), delegating to the existing audited use
cases:
- `POST access/role-assignments/` → `AssignRole`
- `POST access/channel-grants/` → `GrantChannelManagement`

The guardian gateway now **translates ORM "does not exist" into access domain
exceptions** (`SubjectNotFoundError`, `RoleNotFoundError`) so the application and
interface layers never see Django's `DoesNotExist`. The views map them to
`404` (unknown user/channel) and `400` (unknown role). Only roles that exist as
Groups (i.e. registry-declared roles) can be assigned, which is a natural
allow-list.

### RBAC events are now audited
`AssignRole` and `GrantChannelManagement` take an `AuditRecorder` and write
durable entries (`access.role_assigned`, `access.channel_management_granted`).
The audited resource is the **subject user** whose access changed; the actor is
the acting administrator's stable id (never PII). A rejected assignment writes
nothing.

### Audit read API (CQRS-style split)
Reading is a separate port from writing: `AuditQuery` (read) alongside
`AuditTrail` (append-only write). `ListAuditEntries` owns the paging policy — a
default page size and a hard ceiling, so the endpoint can never be coerced into
an unbounded scan — over `DjangoAuditReader`, which maps rows back to domain
`AuditEntry` objects. `GET audit/entries/` (gated by `manage_access`, since
reading the trail is security oversight) lists newest-first with optional
`resource_type` / `resource_id` / `action` / `limit` filters.

## Update (2026-07-02) — user list/create
The access-admin surface previously operated on raw numeric user ids, because
there was no way to enumerate or create accounts outside OTP self-registration
(recorded as a deferral in ISSUES.md). Two endpoints close that gap under the same
`manage_access` gate:

- `GET /access/users/` — a paginated, id-ordered list of accounts
  (`ListUserAccounts` use case → `UserDirectory.list_accounts`), projected as the
  framework-free `UserAccount` read model (no secrets). It backs the admin panel's
  user **picker** so roles/grants target a chosen account, not a typed id.
- `POST /access/users/` — an admin creates an account directly
  (`AdminCreateUser`), bypassing the OTP round-trip a self-registering shopper
  goes through. The phone number is validated/canonicalised by the domain value
  object; the password is write-only (never echoed) and never logged; the creation
  is audited (`user.created`). A duplicate phone is a 409, an invalid phone a 400.

No migration: `UserDirectory` gained `list_accounts`/`get_account` and an
`is_staff` flag on `create`, all served by the existing `User` model.

## Consequences
- **Positive.** Phase 1's access story is complete end-to-end: roles and scope
  can be administered over HTTP, every grant is on the durable trail, and the
  trail is queryable. The dependency rule holds — new ports (`AuditQuery`) and
  domain exceptions keep the ORM/guardian behind the boundary; the use cases stay
  unit-tested against fakes; coverage is 100%.
- **Negative / deferred.** No UI; these are API-only. Listing is offset-free
  (limit + filters only) — cursor pagination can come with the dashboard.
- **Migration.** `identity/0003_alter_user_options` adds the `manage_access`
  permission to the `User` content type.
- **PII.** Unchanged from ADR 0008: actors are stable ids and change values are
  JSON scalars chosen per call site (here: role name, channel slug). No phone /
  email / secret ever enters a change value.

## Notes
- The plugin **entry-point** mechanism for third-party permission registration
  (floated in ADR 0007) is still deferred; the in-process registry already
  supports multiple contexts (channel + identity now both contribute), which is
  all Phase 1 needs.
- **Transactional audit** for the RBAC grants is not adopted here: like channel
  config, an access grant writing its audit entry just after commit is acceptable.
  Money/inventory remain the cases that must share one transaction with their
  audit entry, via the Phase 3 Unit of Work (see ADR 0008).
