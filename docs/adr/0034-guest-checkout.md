# ADR 0034 — Guest checkout (inline shipping + guest orders)

- Status: Accepted
- Date: 2026-07-03

## Context
[ADR 0033](0033-guest-cart-ownership.md) let an anonymous guest own a cart, identified by a
server-minted `guest_session` cookie, and deliberately left the order context untouched
(Slice A). This ADR records **Slice B**: turning that guest cart into a placed order and
de-gating the storefront so a guest can complete the purchase in the browser. (Slice C —
merging a guest's cart into their user cart on sign-in — remains.)

Two gaps stood between a guest and a placed order:

- **Order ownership.** `OrderModel` keyed every order on a hard user FK, and the order
  repository/cart bridge decoded the owner as a bare user pk. A guest owner (`g:<token>`)
  had nowhere to live.
- **The shipping address.** Checkout captured its shipping address from the shopper's
  address book (ADR 0031/0032). A guest has no address book.

## Decision

### Orders gain the same dual-column ownership as carts
`OrderModel` now mirrors the cart's Slice-A ownership exactly: the user FK becomes
**nullable**, a nullable `guest_token` column is added, and a `CheckConstraint`
(`order_exactly_one_owner`) enforces that exactly one is set. The order repository, cart
bridge, and mappers decode the application's opaque `owner` string (`u:<pk>` / `g:<token>`)
by splitting on `:` — the same contract the cart uses and the HTTP boundary produces — so
the domain and application layers stay unaware of which column stores the owner (the
dependency rule holds; infrastructure never imports the interface). A guest-history index
(`idx_order_guest_recent`) matches the existing user one. Existing user orders satisfy the
constraint with no data migration.

The address reader is the one adapter that stays user-only: a guest owns no saved
addresses, so `get_for_owner` short-circuits to "not found" for a `g:` owner rather than
attempting a user-pk decode. Guests never reach it on the happy path (they check out
inline); a guest who nonetheless sends a saved `address_id` is refused (400), exactly like
an unknown address.

### The shipping address arrives one of two ways — exactly one
`PlaceOrderCommand` now carries **either** a saved `address_id` (a signed-in shopper picks
one from their book, resolved and snapshotted as before) **or** an inline
`InlineShippingAddress` (a guest's one-off form), never both, never neither. The use case
captures whichever is present onto the order; supplying neither is refused as an unknown
address. The order's `ShippingAddress` value object re-validates presence/length either
way, and the transport serializer validates the inline form's Iranian mobile + 10-digit
postal formats (the address context that normally owns those rules is not on a guest's
path). The captured "contact" is the recipient name + phone the form already collects —
no separate contact field, matching the phone-first identity model.

### The order endpoints move to `AllowAny`
`OrderCollectionView`, `OrderDetailView`, and `OrderCancelView` move from
`IsAuthenticated` to `AllowAny` and resolve the owner per request via `resolve_owner`
(no cookie is ever minted here — a guest reaching checkout already holds one from building
their cart; a cookieless request resolves to a throwaway owner that owns nothing, so it
reads empty and cannot place). The now-impossible `401` responses are dropped from the
schema. There is still no owner id in any URL and the order number is opaque, so a guest
and a user alike can reach only their own orders (IDOR stays structurally impossible).

### The storefront de-gates cart, checkout, and order views
The cart, checkout, order-confirmation/detail, and order-history pages no longer gate on a
signed-in user; each resolves its data from the request owner (user or guest cookie). A
guest sees an **inline shipping form** at checkout (reusing the address-book form
component) instead of a saved-address chooser, reviews, and places the order, landing on
the same confirmation a user sees. The header exposes the cart to everyone; the
orders/addresses/account links stay signed-in-only (a guest reaches their order via the
post-checkout redirect).

## Consequences
- A visitor can complete a full purchase — browse → cart → inline shipping → order — with
  no account, identified only by their HttpOnly session cookie. The money/inventory path
  (price capture, atomic stock deduction under the Unit of Work, snapshotted totals) is
  unchanged; only the owner and the address source differ.
- Backwards-compatible: existing user orders keep their FK owner and `NULL` `guest_token`,
  satisfying the new constraint with no data migration.
- Verified by unit tests (inline capture, exactly-one address source, guest owner audit),
  real-DB integration tests (guest order round-trip by token, guest/user isolation, guest
  checkout end to end, a guest refused a saved `address_id`), and a full-stack Playwright
  spec driving the guest journey in a real browser (build cart → inline checkout → order
  confirmation → history → a different guest is refused (IDOR) → cancel/restock).
- Guest orders are not reaped by a user cascade; the same future cleanup job that expires
  old guest carts (noted in ADR 0033) should expire old guest orders. Not built here.
- Slice C (merge a guest's cart into their user cart on sign-in) remains.
