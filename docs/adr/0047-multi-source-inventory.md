# ADR 0047 — Multi-source inventory + reservation at checkout (Phase 5, inventory slice)

- Status: Accepted
- Date: 2026-07-11

## Context
Until now stock has been a single non-negative count per variant (`catalog_variant_stock`,
one row per variant), deducted on-hand when an order is placed and restored on cancel
(Phase 2 "simple inventory" + Phase 3 checkout). The variant-stock table was deliberately a
one-to-one *facet* of the variant precisely so it could "later grow into the multi-warehouse
(MSI) model without reshaping the variant table" — this slice is that growth.

Phase 5's stated output is an order with **reserved multi-source inventory** visible at
checkout. This slice introduces the real model — **stock sources** (warehouses) and
**per-source stock levels** with a distinct **reserved** counter — and switches checkout from
"deduct on-hand" to "**reserve**", the semantics fulfilment (Phase 6) will later settle. It is
deliberately the **smallest coherent MSI increment**: a real multi-source, reserve/release
model with a single seeded default source, on the same port/adapter discipline the shipping and
tax slices used. Threshold/alerts, backorder, and the source-selection *strategy* beyond
"highest-available-first" are deferred to later slices that plug into this seam.

## Decision

### A new `inventory` bounded context (source of truth for stock)
A full Clean-Architecture context (`domain` / `application` / `infrastructure` / `interface`):

- **Domain**
  - `StockSourceCode` (a slug-shaped code) and a `StockSource` entity (code, name).
  - `Quantity` value object (non-negative bounded int — the context owns its own, it does not
    import the catalog's `StockQuantity`).
  - `StockLevel` entity: `(sku, source_code, on_hand, reserved)` with the invariant
    `0 <= reserved <= on_hand`; `available = on_hand - reserved`.
  - Domain services: `available_to_promise(levels)` sums `available` across a variant's levels;
    `plan_reservation(levels, quantity)` returns an ordered `[(source_code, qty), …]` plan drawing
    from the most-available source first (deterministic on ties by source code), or raises
    `InsufficientStockError` **before any movement** — the overselling guard lives in the domain.
  - Exceptions: `InvalidQuantityError`, `InvalidStockLevelError`, `InsufficientStockError`,
    `StockSourceNotFoundError`.

- **Application**
  - Ports: `StockLevelRepository` — `levels_for(sku)`, and the two atomic, row-locked mutators
    `reserve(plan)` / `release(sku, quantity)` (release unwinds reservations most-reserved-first);
    `set_on_hand(sku, source, quantity)` / `adjust_on_hand(sku, source, delta)` for the physical
    count; `available(sku)`. `StockSourceRepository` for source CRUD/list.
  - Use cases: `ReserveStock` (reserve N of a sku, atomic), `ReleaseReservation`,
    `GetAvailability` (available-to-promise), and `SetStockOnHand`/`AdjustStockOnHand` (admin
    physical adjustments, audited — inventory-sensitive).

- **Infrastructure**
  - `inventory_stock_source` and `inventory_stock_level` tables (`unique(sku, source)`).
    `reserve`/`release`/`adjust` run the read-modify-write under `select_for_update()` on the
    level rows (per-source row lock) inside `transaction.atomic()`, so two concurrent checkouts on
    the last unit serialize and cannot both reserve it (the anti-overselling guarantee, now at the
    level row instead of the variant row).
  - A data migration creates a default `main` source and copies every existing
    `catalog_variant_stock.quantity` into a `main` level as `on_hand` (`reserved = 0`), so no stock
    is lost and behaviour is unchanged for a single-source store.

- **Interface** — admin endpoints to list sources and read/set/adjust a variant's per-source
  levels are **deferred to slice 2** (which also binds warehouse access-scope); this slice keeps
  the public surface unchanged and drives inventory through the existing catalog stock endpoints.

### Existing contexts bridge to inventory (no API churn)
- The catalog's `DjangoStockRepository` (`get_quantity`/`set_quantity`/`adjust_quantity`) is
  **re-backed** onto the inventory context's default source: physical on-hand at `main`. Its
  public interface is unchanged, so the admin stock endpoints, `seed_demo`/`seed_e2e`, and their
  tests keep working verbatim — the multi-source model lives underneath.
- The storefront availability query (PLP/PDP "buyable") switches from `stock__quantity__gt=0` to
  **`available > 0`** (on-hand minus reserved) computed from the inventory levels, so a fully
  reserved variant reads as out of stock.
- The order context's `Inventory` port keeps `deduct`/`restock` **names** but its adapter
  (`DjangoInventory`) now bridges to `ReserveStock`/`ReleaseReservation`: placing an order
  **reserves** (on-hand unchanged, reserved += qty), cancelling **releases**. Overselling is
  refused against **available**, translated to the order's `OutOfStockError`. This changes what
  cancel restores (a released reservation, not a re-incremented on-hand) but preserves the
  buyable outcome; the affected order/E2E stock assertions are updated as part of this slice.

## Consequences
- Stock is now genuinely multi-source with a reserved/available split, reserved at checkout and
  released on cancel, guarded against overselling at the per-source level row under a lock. Adding
  more sources, a smarter source-selection strategy, thresholds/alerts, and backorder are additive
  slices on this seam — not a domain rewrite. The physical on-hand admin surface is unchanged.
- **Migration**: existing single-count stock is folded into a `main` source (on_hand), reserved
  starts at `0`; in-flight pending orders predate reservation tracking, so their historical on-hand
  deduction is not retro-converted (documented; the count is consistent going forward).
- **Testing**: unit tests cover the inventory domain (quantity/level invariants, ATP,
  reservation-plan incl. insufficient + tie determinism) and use cases (reserve/release/adjust
  against fakes, idempotent-free atomicity); integration tests cover the level repository under
  concurrency (two reservers on the last unit — exactly one wins), the catalog-stock bridge, the
  storefront availability-through-reserved query, and checkout reserving/releasing; E2E re-runs the
  purchase flow (reserve on place, release on cancel) and asserts a fully reserved variant is not
  buyable.
- **Deferred (later Phase 5 slices)**: admin MSI panel + per-source editing (slice with warehouse
  access-scope), stock thresholds/low-stock alerts, backorder, and source-selection strategies
  beyond highest-available-first.
