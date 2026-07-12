# ADR 0049 — Per-variant stock policy: opt-in backorder + low-stock alerts (Phase 5, inventory slice)

- Status: Accepted
- Date: 2026-07-12

## Context
Slice 1 (ADR 0047) made the per-source `StockLevel` the source of truth and enforced a
hard no-overselling guarantee at three layers: the `plan_reservation` domain guard, the
adapter's row lock, and a database `CheckConstraint reserved <= on_hand`. Phase 5 also
asks for **low-stock alerts** and **backorder** — and backorder is *intentional
overselling*: a flagged variant must be orderable beyond its physical stock. That
directly conflicts with the slice-1 invariant.

## Decision
Keep the physical invariant intact and model backorder as a **separate, opt-in policy**,
so overselling is never implicit and the DB backstop is never weakened.

- **New `StockPolicy` (domain) / `StockPolicyModel` (one row per SKU).** Carries
  `backorderable` (may this variant be sold past on-hand?), `low_stock_threshold` (alert
  at/below this available count; 0 disables), and `backordered` (units currently promised
  with no physical backing). Absent row ⇒ the safe default (no backorder, no alert).
- **Two buckets, invariant preserved.** Physical reservations still live on the level and
  still satisfy `reserved <= on_hand` (the `CheckConstraint` is unchanged). The backorder
  overflow is tracked on the *policy*, never on a level — so a backorder can never push a
  level past its physical count.
- **`plan_reservation` gained `backorderable`.** A non-backorderable variant short of
  stock is still refused whole with `InsufficientStockError` (unchanged). A backorderable
  one reserves all physical available stock and returns the shortfall as
  `ReservationPlan.backordered`. The signature changed from returning a `list` to a
  `ReservationPlan` (lines + backordered).
- **Release frees backorder first, then physical** (LIFO: the backorder was the last thing
  promised), so releasing a backordered order unwinds cleanly.
- **Low-stock alert** is a pure `is_low_stock(available, threshold)` predicate; the adapter
  emits a structured `stock_low` warning after any reserve/set/adjust that leaves available
  at/below the threshold. (Alerts are logs this slice; a notification channel is later.)
- **Storefront availability** now treats a backorderable SKU as buyable even at zero
  available-to-promise (`available > 0 OR backorderable`).
- **Admin surface.** `GET/PUT /inventory/policies/<sku>/` reads/sets a variant's policy —
  platform-global config, so it requires the global `manage_stock_source` permission (never
  per-source). The SKU is validated against the catalog (no policy for a ghost variant). A
  negative threshold is a 400; setting a policy never disturbs the in-flight `backordered`
  count. `inventory.policy_set` is audited.

## Consequences
- Overselling is explicit, per-variant, and auditable; a normal variant behaves exactly as
  before, and the database constraint that guarantees `reserved <= on_hand` is untouched.
- Checkout is transparently backorder-aware: the order `Inventory` bridge calls `reserve`
  unchanged, and a backorderable OOS variant now places instead of raising `OutOfStockError`.
- **Deferred:** a notification channel for low-stock (email/webhook — this slice logs);
  surfacing "backorder"/ETA on the PLP/PDP UI (the storefront only knows buyable/not this
  slice); and settling backorder against incoming stock (a fulfilment/Phase-6 concern).

## Alternatives considered
- *Relax the `CheckConstraint` for flagged items (allow `reserved > on_hand`).* Rejected —
  it weakens the one database-level guarantee against overselling for *all* rows and mixes
  physical truth with promises on the same counter. The two-bucket model keeps the physical
  level honest.
- *A boolean column on the catalog variant.* Rejected — stock policy is inventory-context
  state, not catalog config; keeping it in the inventory context preserves the bounded-context
  boundary (the level table already keys by SKU string, not a catalog FK).
