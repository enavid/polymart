# ADR 0008 — Basic audit log

- Status: Accepted
- Date: 2026-06-28

## Context
Phase 1 requires a **basic audit log**: a durable record of *who* changed *what*
*when*. Until now, sensitive mutations emitted only structured logs (structlog),
which are ephemeral observability signals — fine for tracing a request, wrong as
a system of record. Channel mutations in particular gate currency/pricing and can
take a storefront offline (deactivation), so they need a trail that outlives the
log retention window and is queryable by resource.

The roadmap also asks (in the RBAC slice) that sensitive events keep a *separate*
audit trail recording who/when and the before/after values — distinct from the
debug logs.

## Decision

### A framework-free audit context
- **Domain (`domain/audit/`)** owns two pure value objects:
  `FieldChange` (one field's `before`/`after`, restricted to JSON scalars) and
  `AuditEntry` (action, resource type/id, actor, `occurred_at`, and a tuple of
  field changes). Both self-validate: the action must be a dotted, namespaced
  event (`channel.status_changed`) so the trail stays greppable by area; the
  timestamp must be timezone-aware; the actor, when present, must not be blank.
- **Application (`application/audit/`)** exposes two levels of abstraction:
  - `AuditRecorder` — the high-level seam other use cases depend on. They say
    "record this change" and supply only business facts.
  - `AuditTrail` (append-only persistence) and `Clock` — the low-level ports the
    default `PersistentAuditRecorder` is built from. It stamps the time and
    assembles the `AuditEntry`, then forwards it to the trail.
  Splitting them keeps each use case's dependency to a single, intent-revealing
  collaborator while staying fully testable against fakes.
- **Infrastructure (`infrastructure/audit/`)** provides `DjangoAuditTrail`
  (append-only inserts into an `audit_log` table; `changes` stored as
  `{field: {"before": ..., "after": ...}}` JSON) and a `SystemClock`.

### First consumer: channel mutations
Mirroring how the RBAC slice landed on the channel context first, the audit log's
first consumers are the two sensitive channel use cases:
- `CreateChannel` records `channel.created` (after-only values: slug, currency,
  is_active).
- `SetChannelStatus` records `channel.status_changed` with the `is_active`
  before/after. A no-op status change records nothing (there was no change).
Both pass the acting user's **stable id** (never the phone number / PII) as the
actor, sourced from the same `_actor(request)` helper the structured logs use.

The recorder is wired through the channel composition root, so the endpoints get
the real trail and clock; unit tests inject a `FakeAuditRecorder`.

### What is NOT in this slice (deliberately deferred)
- **A read/admin API** for the trail. Capturing the trail is the Phase 1
  requirement; an admin surface to browse it is a later increment (consistent
  with the RBAC slice, which also deferred its admin assignment API).
- **Auditing the RBAC events** (`AssignRole`, `GrantChannelManagement`). The
  recorder is generic; extending coverage to those is just more `record(...)`
  calls and lands with the admin surface.
- **Transactional audit.** Today each channel repository call commits in its own
  `transaction.atomic()` and the audit entry is written *after* that commit, in a
  separate transaction. For channel configuration this best-effort-after-commit
  posture is acceptable. **Money/inventory mutations must instead share one
  transaction with their audit entry**, which requires use-case-controlled
  transactions (a Unit of Work). That is already slated for Phase 3; audited
  money mutations must adopt it rather than the current pattern.

## Consequences
- **Positive.** Sensitive channel changes now leave a durable, queryable trail
  with who/when and before/after. The domain is pure and fully unit-tested; the
  ORM stays behind the `AuditTrail` port. The `AuditRecorder` seam lets any future
  context audit a change by depending on one abstraction. End-to-end coverage runs
  through the real HTTP path (create + status change write rows).
- **Negative / deferred.** No way to *read* the trail via the API yet. RBAC events
  are not audited yet. Audit is not transactional with the mutation (see above);
  this is safe for configuration but must change for money/inventory in Phase 3.
- **Migration.** `audit/0001_initial` creates the `audit_log` table with indexes
  on `(resource_type, resource_id, -occurred_at)` and `(action, -occurred_at)`.
- **PII.** The actor is a stable user id, and `FieldChange` values are restricted
  to JSON scalars chosen by each call site. Call sites must never put PII (phone,
  email, secrets) into a change value; the channel events carry only
  slug/currency/is_active.

## Notes
- `SystemClock` is a deliberate twin of the identity clock: each bounded context
  owns its own `Clock` port so the application layers stay decoupled, and the
  adapter is a trivial one-liner.
