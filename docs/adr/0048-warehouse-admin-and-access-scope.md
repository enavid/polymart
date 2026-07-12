# ADR 0048 — Warehouse admin API + per-source access-scope binding (Phase 5, inventory slice)

- Status: Accepted
- Date: 2026-07-12

## Context
ADR 0047 introduced the `inventory` bounded context (stock sources + per-source levels)
as the source of truth for stock, but left it with **no HTTP surface**: sources are only
created by migration/seed and stock is only managed through the catalog's single-count
`manage_catalog` endpoints (which operate on the default `main` source). Phase 5 also
carries a **Phase-1 debt**: the two-layer RBAC model always intended object-scoped
*warehouse* management (a user who manages only their warehouse), deferred until the
warehouse context existed.

These two are the same slice: object-scoped warehouse management has nothing to enforce
on until warehouse-management endpoints exist, and a warehouse admin API without scoping
would either be all-or-nothing or grow scoping later as a breaking change. Shipping them
together avoids dead code (a grant/check with nothing to guard) and a later rework.

## Decision
Add a **staff inventory admin API** and bind **per-source access scope** to it, on the
same two-layer RBAC pattern the channel context established (a single permission usable
globally via a role *or* per-object via django-guardian).

- **Permission & role.** The inventory context owns `manage_stock_source`
  (`src/domain/inventory/permissions.py`), declared on `StockSourceModel.Meta.permissions`
  so `create_permissions` binds it to that content type (the object type a per-source
  guardian grant attaches to). The registry registers it and an `inventory_admin` role
  (global "manage every source"). Migration `inventory/0003` records the model option.
- **Gateway.** `AccessControlGateway` gains `grant_stock_source_management` and
  `can_manage_stock_source`; `GuardianAccessControl` implements them exactly like the
  channel pair (global role/superuser short-circuit, then the per-object grant).
- **Grant use case + endpoint.** `GrantStockSourceManagement` (in the access application,
  beside `GrantChannelManagement`) resolves a source code → id via the inventory
  `StockSourceRepository`, grants object scope, and audits `access.stock_source_management_granted`.
  Exposed at `POST /access/stock-source-grants/` (gated by `manage_access`).
- **Admin endpoints.**
  - `GET/POST /inventory/sources/` — list sources (auth) / create a source
    (global `manage_stock_source`; a duplicate code → 409, a malformed code/name → 400).
  - `GET/PUT/PATCH /inventory/sources/<code>/stock/<sku>/` — read / set / adjust a
    variant's physical on-hand at one source. Writes are authorised **globally or
    per-source**: the view resolves the source (a missing source → 404, not 403) and calls
    `check_object_permissions` with the domain `StockSource`, so a scoped manager may
    mutate only the source granted. Setting below what is reserved, or over-withdrawing,
    is a 409; an unknown source or variant is a 404.
- **Cross-context validation.** The stock endpoints validate the SKU is a real variant
  (via the catalog `GetVariant`) so the admin cannot create an orphan level for a
  non-existent variant — interface-level composition, not a domain dependency.
- **Audit.** Physical-stock changes are inventory-sensitive: `SetStockOnHand`/
  `AdjustStockOnHand` now take an `AuditRecorder` and write a before/after entry
  (`inventory.stock_set` / `inventory.stock_adjusted`, resource `sku@source`), and
  `CreateStockSource` audits `inventory.source_created`. The adjust before-value is derived
  from the locked result (`after − delta`), never a second unlocked read.
- **Entity id.** `StockSource` gained an `id` (its persistence identity) — the handle the
  scope grant and object-permission check bind to.

## Consequences
- Warehouse management is now a real, RBAC-scoped surface, and the Phase-1 warehouse
  access-scope debt is closed on the same seam as channel scope.
- The physical-stock admin path now has a durable, per-source audit trail (the catalog's
  single-count endpoints keep their own variant-level trail).
- **Deferred:** the storefront/admin **panel UI** for warehouses (this slice is the
  backend API, covered end-to-end by integration tests hitting the full request path);
  source-selection strategy beyond highest-available; and moving the catalog stock
  endpoints onto this API (they remain the simple single-source surface for now).

## Alternatives considered
- *Binding capability without endpoints* (grant + check now, enforcement later): rejected —
  it leaves `can_manage_stock_source` and the DRF scope class as dead code until a future
  slice, violating the no-dead-code rule.
- *A separate permission per action (create vs set-stock):* rejected — the channel
  precedent uses one permission at both layers; a single `manage_stock_source` keeps the
  model consistent and the registry simple.
