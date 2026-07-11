# ADR 0035 — Guest cart merge on login (slice C)

- Status: Accepted
- Date: 2026-07-03

## Context
[ADR 0033](0033-guest-cart-ownership.md) gave an anonymous guest a cart (slice A) and
[ADR 0034](0034-guest-checkout.md) let a guest place an order (slice B). One gap
remained: a shopper who filled a cart as a guest and *then* signed in lost that cart —
the guest cart (keyed by the `guest_session` token) and the user cart (keyed by the
user pk) are different rows, and login simply started reading the user's. This ADR
records **slice C**: folding the guest cart into the user cart on login. It completes
guest checkout, and with it the substantive cart→order surface of Phase 3.

## Decision

### The merge rule lives in the Cart aggregate
`Cart.merge_from(other)` absorbs another cart's lines: a variant present in both carts
has its quantities **summed**, a variant only in the guest cart is **appended**, and the
user cart's existing lines keep their order. The sum is *capped* at the maximum line
quantity via a new `CartQuantity.capped_sum` (as opposed to `plus`, which rejects an
over-large total): a login must never fail because a guest and a user each happened to
hold an absurd quantity of the same SKU. Pure structure, no pricing, no I/O — pricing is
still resolved at read time as everywhere else.

### The repository merges atomically, per the owner-decode contract
`CartRepository.merge_guest_into_user(guest_owner, user_owner) -> int` merges every
channel the guest owns a cart in and returns the count. The Django adapter runs the whole
thing in one `transaction.atomic()`: it locks the guest carts (`select_for_update`),
absorbs each into the same-channel user cart (load-or-create under the existing row lock,
`merge_from`, replace lines), and deletes the guest cart — together, so a merged guest
cart is never left behind to be merged twice. It is **idempotent**: a repeat finds no
guest carts and merges nothing (returns 0), so a double-submitted login is harmless. The
guest lock also blocks a concurrent guest write from slipping a line in between the read
and the delete. Owner ids stay the opaque `u:<pk>` / `g:<token>` strings decoded by
splitting on `:`, exactly as slices A/B.

### Login triggers the merge, best-effort, then spends the guest cookie
`LoginView` resolves the guest token from the `guest_session` cookie (if any) and runs
`MergeGuestCart` after authentication succeeds. The merge is **best-effort**: any failure
is logged (`guest_cart_merge_failed`) and swallowed so a cart problem can never break
sign-in, and the guest cookie is *kept* in that case so the cart is not silently lost.
On success the guest cookie is cleared (`clear_guest_cookie`) — the guest identity is
spent. The `guest_cart_merged` log records the user id and the channel count but **never
the guest token**, which is a session credential (consistent with the slice-A/B logging
posture and the standing ISSUES.md note on guest-token logging).

### The storefront refetches the merged cart
The login mutation invalidates the `["cart", …]` query, so the cart the shopper viewed as
a guest (cached client-side) is dropped and the merged cart is refetched under the new
session. No other UI change: the merge is transparent — the shopper simply keeps their
items.

## Consequences
- A shopper who builds a cart anonymously and then signs in keeps it; quantities combine
  for a shared SKU, and multiple channels are handled.
- Backwards-compatible and safe under retries (idempotent), with no data migration.
- Verified by unit tests (`merge_from` / `capped_sum`, and the `MergeGuestCart` use case
  including that the raw token is never logged), real-DB integration tests (merge into an
  empty and a non-empty user cart, cross-channel merge, guest-cart deletion, idempotency),
  login endpoint tests (cart merged + cookie cleared, no cookie touched without a guest
  session, a failing merge never breaks login), a frontend test (cart query invalidated on
  login), and a full-stack Playwright spec (build a cart as a guest → sign in → the line is
  in the user's cart).
- Guest checkout (slices A–C) is complete. The remaining Phase 3 item is manual /
  pre-invoice orders; event-bus publication of `OrderPlaced`/`PaymentCaptured` stays
  deferred to the payments phase.
