# ADR 0036 — Manual orders and printable pre-invoice

- Status: Accepted
- Date: 2026-07-03

## Context
This is the last substantive Phase 3 item. Alongside a shopper's self-service checkout,
staff need to create an order **for** a customer — a phone order, an in-person sale, a
quote — and hand the customer a **pre-invoice** (proforma) to pay against. Everything the
order aggregate already does (capture prices, deduct stock atomically under the unit of
work, snapshot the shipping address, the state machine, the audit trail) should be reused;
only the *entry point* differs (staff-supplied lines instead of a cart) and a *printable
projection* is added.

## Decision

### A manual order is a real pending order, created by staff
A new use case `CreateManualOrder` builds a `PENDING` order directly from staff-supplied
lines (a list of sku + quantity) and an inline shipping address — the same capture/deduct
path as checkout, minus the cart. It reuses the shared `_capture_and_deduct` helper (now
extracted so `PlaceOrder` and `CreateManualOrder` share one price-capture-and-stock-deduct
implementation), `build_order_lines`, and `order_total`, and runs inside the same
`UnitOfWork` so an oversell rolls the whole thing back. The creation is audited
(`order.created_manually`, with an `origin=manual` field). Because a manual order is a
real pending order, it deducts stock and is cancellable (restocking) exactly like any
other — no separate lifecycle.

The order is **owned by the creating staff** (`u:<staff_pk>`), which satisfies the
model's exactly-one-owner constraint and lets that staff member read/manage it; the
customer is identified by the captured shipping contact (recipient + phone), matching the
phone-first identity model. The Order aggregate gained one invariant — a variant appears
at most once per order (`DuplicateOrderLineError`) — since a manual order takes an
arbitrary line list (a cart-sourced order could never duplicate); the persisted
`unique(order, sku)` enforces the same at the database.

### The pre-invoice is the printable projection of any pending order
`GetOrderForInvoice` reads an order by number **without** owner-scoping — a staff member
issuing a proforma may print it for any order, not only ones they created. This is *not*
IDOR: it is reachable only behind the new `manage_orders` permission (there is no
owner-derived access here; authorization is the permission). The pre-invoice body is the
order plus a `document_type` marker and a `tax` placeholder (`null` — tax is computed in a
later phase — with `grand_total` equal to the order total for now, so the printable
document is forward-compatible).

### A dedicated, permission-gated staff surface
Two endpoints, both gated by `OrderManagePermission` (`manage_orders`):
`POST /orders/manual/` (create) and `GET /orders/<number>/pre-invoice/` (read). The
`manual/` route is declared before the `<number>/` detail route so "manual" is never read
as an order number. `manage_orders` is a new permission **owned by the order context**
(declared on the order content type, collected by the RBAC registry) with an `order_admin`
role; the seed grants it to the E2E staff user. The serializer rejects an empty or
duplicated line list (a clean 400) with the domain invariant as a defensive net behind it.

### A printable admin UI
`/admin/orders/new` is a staff form (channel, dynamic sku+quantity line rows, an inline
shipping address) that creates the order and navigates to
`/admin/orders/<number>/pre-invoice` — a print-friendly proforma (order number, Jalali
issue date, captured recipient/address, line table, tax placeholder, grand total) with a
Print button hidden on paper (`@media print`). Every money value is the exact server
string, never recomputed client-side.

## Consequences
- Staff can create an order for a customer and print a pre-invoice; it is a normal pending
  order (deducts stock, cancellable/restockable, audited), so no new lifecycle or reaping
  rules are needed.
- The order price-capture/stock-deduct logic is now shared by checkout and manual creation
  (DRY), and the Order aggregate rejects a duplicated variant everywhere it is built.
- Verified by unit tests (the aggregate invariant; `CreateManualOrder` capture/deduct/audit/
  rollback/duplicate/empty/unknown-channel/unpriced; `GetOrderForInvoice` un-scoped read),
  real-DB integration tests (the un-scoped `get`; the endpoints incl. permission 401/403,
  oversell 409, duplicate/empty 400, and a staff pre-invoice for a guest's order), frontend
  tests (the form submits and navigates; the pre-invoice renders server totals + tax
  placeholder + error state), and a full-stack Playwright spec (staff create a manual order
  and reach its printable pre-invoice, then cancel to restock).
- With this, **Phase 3 (cart → checkout → order) is complete** on the backend and in the UI.
  The remaining `OrderPlaced`/`PaymentCaptured` event-bus publication stays deferred to the
  payments phase (Phase 4); `order.*` events are audited and logged today.
