# ADR 0007 — Two-layer RBAC and a permission registry

- Status: Accepted
- Date: 2026-06-28

## Context
Phase 1 requires "users with different access levels". CLAUDE.md fixes the shape:
a **two-layer RBAC** model — a role layer (Django Groups + custom permissions)
and an object/scope layer (django-guardian) — plus a **permission registry** so
new contexts (and future plugins) can contribute permissions without touching the
enforcement code. The Channel context is the first consumer: until now, writes to
`channels/` were an interim staff-only gate (`IsAdminUser`, see ADR 0004). This
slice replaces that with a real channel-scoped permission and lays down the RBAC
machinery the rest of the platform will reuse.

Channels are platform configuration — deactivating one takes a storefront offline
— so write authorisation must be precise: some operators manage every channel,
others only the one or two they own.

## Decision

### A pure-domain permission registry
- **Domain (`domain/access/`)** owns the catalogue as framework-free Python:
  `PermissionDefinition` (a codename, a label, and a `resource` that maps to a
  Django app-label), `RoleDefinition` (a named bundle of permission codenames),
  and `PermissionRegistry` which collects both with integrity guarantees
  (no duplicate codenames/roles; a role may only reference known permissions).
- **Each context owns its permissions.** `domain/channel/permissions.py` declares
  `manage_channel`; `domain/access/registry.py` assembles the default registry and
  the base `channel_admin` role. Adding a context means registering its
  permissions there — enforcement code is untouched.

### Two layers, one permission
`manage_channel` is deliberately a single, object-capable permission used at both
layers:
- **Role layer (global):** the `channel_admin` Group carries `manage_channel`.
  A member manages *every* channel, including creating new ones.
- **Object layer (scope):** django-guardian grants `manage_channel` on a *single*
  `ChannelModel` instance. The holder manages only that channel.

### Application + infrastructure
- **Application (`application/access/`)** exposes the `AccessControlGateway` port
  and two use cases — `AssignRole` and `GrantChannelManagement` — that work in
  plain ids and emit audit-ready structured logs (`role_assigned`,
  `channel_management_granted`). No framework imports.
- **Infrastructure (`infrastructure/access/`)** provides `GuardianAccessControl`
  (Groups for roles, guardian `assign_perm`/`has_perm` for object scope) and
  `sync_access_control`, which projects the registry onto Django Groups. The sync
  runs on `post_migrate` (so the role layer is always in step with the registry,
  including in the test DB) and is idempotent; it force-creates content
  types/permissions first to stay independent of app-migration ordering.

### Enforcement on the channel endpoints (interface)
Reads stay open to any authenticated user. Writes split by surface:
- **Create** is platform-global (no object exists yet) →
  `GlobalChannelManagePermission` requires the permission globally.
- **Mutate an existing channel** may be authorised globally *or* per-object →
  `ScopedChannelManagePermission` authenticates in `has_permission` and defers the
  precise decision to `has_object_permission`, which the detail view triggers via
  `check_object_permissions(request, channel)`. The view resolves the channel
  first, so a missing one is a `404` (its existence is already visible to any
  authenticated reader), and only then enforces scope.

### Supporting settings
- `guardian.backends.ObjectPermissionBackend` is in `AUTHENTICATION_BACKENDS`.
- `ANONYMOUS_USER_NAME = None`: the API is authenticated-only (anonymous requests
  get `401` before any object check), so guardian's DB-backed anonymous user —
  which would not fit the phone-first custom user — is disabled.

## Consequences
- **Positive.** Channel writes are now genuinely access-controlled at two
  granularities. New permissions/roles are declarative. The domain registry is
  pure and unit-tested; guardian/ORM details stay in infrastructure behind a port.
  Granting/assigning is exercised end-to-end (use case → guardian → endpoint).
- **Negative / deferred.** No admin API yet for assigning roles or per-channel
  scope — the use cases and gateway exist and are tested, but a management
  surface (and binding scope to other resources such as warehouses) lands with a
  later Phase 1 slice. The permission registry is process-local; a plugin
  entry-point mechanism can come when third-party extensions arrive.
- **Migration.** `channel/0002_alter_channelmodel_options` adds the
  `manage_channel` permission to the channel content type.

## Supersedes
- The interim staff-only write gate described in ADR 0004 is replaced by the
  channel-scoped permission model above.
