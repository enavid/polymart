# ADR 0024 — Catalog: simple inventory (on-hand stock per variant)

- Status: Accepted
- Date: 2026-06-29

## Context
The catalog can now describe what is sold and for how much (ADR 0023), but not
*how many are on hand*. This slice adds **simple inventory**: a single on-hand
quantity per variant, with the operations to set and adjust it.

It is deliberately the *simple* model — one global quantity per variant, no
warehouses. Multi-stock inventory (MSI: stock split across locations, with
per-location availability) is a Phase 5 concern; this slice is shaped so it can
grow into that without reshaping the variant table.

Reservation and order-time deduction belong to cart/checkout (Phase 3), not here.
This slice owns only the *count* and the rule that it can never go negative — the
overselling guard the project treats with financial-grade care.

## Decision
- `domain/catalog/` — one value object and one service, no new entity (mirroring
  the price facet of ADR 0023):
  - `StockQuantity` value object: a **non-negative integer** bounded to the stored
    column (≤ 2,147,483,647). A `bool` is rejected explicitly (it is an `int`
    subclass — `True` must never become a quantity of one) and a non-integer is
    rejected outright. Zero is a valid, in-stock-tracked state (out of stock), not
    an error.
  - `adjust_stock(current, delta)` domain service: applies a signed delta and
    refuses to drop below zero, raising `InsufficientStockError` rather than
    clamping — the caller learns the withdrawal could not be honoured. The new
    total is built through `StockQuantity`, so an overflow past the maximum is also
    rejected (`InvalidStockQuantityError`). This is the overselling rule, kept in
    the pure domain.
- `application/catalog/` — a dedicated `StockRepository` port (get / set / adjust)
  and three use cases:
  - `SetVariantStock` — confirm the variant exists (404), build a `StockQuantity`
    (a negative/out-of-range value is a 400), write the absolute quantity, and
    record a `variant.stock_changed` before/after audit entry. Setting an absolute
    value is naturally idempotent.
  - `AdjustVariantStock` — confirm the variant exists (404), delegate the atomic
    signed adjustment (an oversell/overflow is a 400), and record the same audit
    event.
  - `GetVariantStock` — read-only (404 if the variant is unknown); a variant with
    no stock row reads as zero.
- `infrastructure/catalog/` — `VariantStockModel`: a `OneToOneField` to the variant
  (`CASCADE`, related name `stock`) and a `quantity` `PositiveIntegerField`
  (default 0). Modelled as a one-to-one *facet* of the variant rather than a column
  on it so it can later become the per-location MSI table without touching the
  variant. `DjangoStockRepository.adjust_quantity` runs the **whole
  read-modify-write inside one `transaction.atomic()` under `select_for_update()`
  on the variant row**, so two concurrent adjustments cannot both read the same
  starting quantity and lose an update (or oversell). It calls the domain
  `adjust_stock` service for the no-below-zero decision. Migration `catalog/0014`.
- `interface/api/catalog/` — behind the global `manage_catalog` permission:
  - `GET/PUT/PATCH catalog/variants/<sku>/stock/` — read / set (absolute,
    idempotent) / adjust (signed delta, atomic). `PUT` carries `{quantity}`,
    `PATCH` carries `{delta}`; both respond with the current `{quantity}`.

### Where the concurrency rule lives
The atomic read-modify-write (and the row lock that serializes it) is an
infrastructure concern — transactions and locks are the database's, and a use case
must not import Django. So the repository owns the transaction boundary, but the
*business rule* (never below zero) stays in the pure-domain `adjust_stock`, which
the repository calls inside the lock. This is the same split the Phase 3 order-time
deduction will use.

### Status-code mapping
- Reading / setting / adjusting the stock of an unknown variant → **404**.
- A negative or out-of-range absolute quantity, a non-integer field, or an
  adjustment that would oversell (drop below zero) or overflow → **400**.

### Why an absolute set *and* a relative adjust
`PUT` (absolute) is the simple management operation and is idempotent — a retried
request cannot drift the count. `PATCH` (relative) is the operation that actually
needs the lock: a read-modify-write is the classic lost-update race, so it is the
one routed through `select_for_update` and the domain floor rule.

## Consequences
- Every variant has a single, queryable on-hand quantity — the foundation that
  cart availability checks and order-time deduction (Phase 3) will read and
  decrement.
- Concurrent stock adjustments are serialized per variant and can never oversell
  below zero; the lock is verified against PostgreSQL in CI (the suite is hermetic
  on SQLite, which serializes writes anyway, so true row-lock isolation is a
  PostgreSQL property).

### Known limitations / deferrals
- **Single global quantity.** No warehouses / stock locations (MSI) and no
  per-channel stock — Phase 5.
- **No reservation or order-time deduction.** Holding stock for an in-flight cart
  and decrementing on order placement are Phase 3; this slice only sets/adjusts the
  on-hand count, so there is no order path to oversell against yet.
- **No backorder / allow-negative mode and no `track_inventory` flag.** A variant
  is always tracked and never goes below zero; opt-out tracking and backorders are
  later concerns.
