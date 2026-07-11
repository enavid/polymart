# ADR 0032 — Multi-step checkout with a captured shipping address

- Status: Accepted
- Date: 2026-07-02

## Context
ADR 0030 delivered single-step checkout (a "place order" button on the cart) and
ADR 0031 delivered the address book. The remaining Phase-3 UI item was the multi-step
checkout that ties them together: a shopper chooses a shipping address, reviews, then
places the order. An order with no shipping address is not a real order, so this slice
makes checkout require one — which means the order aggregate must *capture* the address,
exactly as it already captures prices.

## Decision

### The order captures the shipping address as a snapshot
A new `ShippingAddress` value object joins the order domain, and the `Order` aggregate
gains a required `shipping_address` field. Like a line's captured `unit_price`, the
address is a **snapshot copied from the owner's address book at placement**, not a
foreign key — so a later edit or deletion of that saved address never rewrites a placed
order's history. `ShippingAddress` re-validates presence and length bounds (mirroring
the address context's stored precision) but deliberately does **not** re-enforce the
Iran-specific phone/postal *formats*: the value was already validated when the address
was saved, and re-owning that rule would couple the order context to the address
context's domain.

### Checkout resolves the address through a narrow port
`PlaceOrderCommand` gains an `address_id`. `PlaceOrder` resolves it through a new
`AddressReader` port (returning a flat `OwnedAddress` DTO, so no address-domain types
leak into the order context) and captures a `ShippingAddress` from it — **before** the
Unit of Work opens, so an invalid address fails fast without touching stock. The
`DjangoAddressReader` adapter reads the address **owner-scoped**: an `address_id`
belonging to another shopper (or one that does not exist) resolves to `None`, exactly
like a wrong-shaped one, so checkout can never ship to — or even confirm the existence
of — another shopper's saved address. A `None` resolution raises
`UnknownShippingAddressError`, which the view maps to `400` alongside the existing
unknown-channel case (a well-formed request-body reference that does not resolve).

### The captured address is persisted alongside the order
`OrderModel` gains seven `shipping_*` columns (six required, `shipping_line2` optional),
filled from the captured snapshot in the same insert as the order and its lines, inside
the checkout Unit of Work. The migration backfills any pre-existing order rows with `""`
one-off (`preserve_default=False`), so the columns stay NOT NULL with no model-level
default going forward — every new order supplies a real address.

### HTTP surface
- `POST /orders/` now requires `address_id` in the body (a missing field is a serializer
  `400`; an unknown/not-owned id is a `400`). The `201`/`404`/detail responses now
  include a `shipping_address` object.

### Storefront UI: a dedicated `/checkout` route
The cart's checkout control changed from a place-order button to a link into a new
`/checkout` page (disabled while any line is unavailable). Checkout is two steps:
1. **Address** — a radio list of the shopper's saved addresses (the default
   preselected), or, if they have none, the address form inline (reusing the
   address-book `AddressForm`). A shopper with no addresses must add one here.
2. **Review** — the chosen address plus the server-computed order summary and total
   (money is the server string, never recomputed), then **place order**.
On success the shopper lands on the order confirmation, which now also renders the
captured shipping address. A place-order conflict (oversell, a line that lost its price)
surfaces a localized message on the review step without navigating — the same
substitution the cart already made, since the backend detail is English.

### Deterministic E2E without cross-spec races
`seed_e2e` now seeds one persistent default "home" address for the shopper (reset to
exactly that baseline each run). The checkout E2E selects that seeded address *by name*
(stable, never deleted), and the address-book E2E was rewritten to work relative to the
baseline and **never delete the seeded address**. This lets the checkout and address-book
specs share the one seeded shopper — which run in parallel workers against the same
backend — without racing on a shared, deleted address.

## Consequences
- **Positive.** Checkout is a realistic multi-step flow, the address book is finally put
  to use, and every placed order carries an immutable record of where it shipped.
  Owner-scoped address resolution keeps IDOR structurally impossible (verified by unit,
  integration, and browser tests, including a cross-account address attempt). Coverage
  stays ~100% on the new order code; money and the captured address round-trip through
  the real database losslessly.
- **Negative / deferred.** Still no guest checkout (an authenticated shopper is required;
  its own Phase-3 bullet) and no manual/pre-invoice order. Editing or removing an address
  *from within* checkout is not offered — the shopper manages addresses in the address
  book; checkout only selects or adds. Shipping cost/method is Phase 5; this slice
  captures *where* to ship, not *how much* shipping costs.
- **Migration.** `order/0002` adds the seven `shipping_*` columns to `order_order`.
- **PII.** The captured address (a person's name, phone, and physical location) lives on
  the order row and is projected to that order's owner only. Structured logs still carry
  just the order number, line count, and currency — never the address or the amount.
