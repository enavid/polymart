# ADR 0033 — Guest cart ownership (anonymous session cookie)

- Status: Accepted
- Date: 2026-07-02

## Context
Guest checkout is the main remaining Phase 3 item. Until now both the cart and order
contexts modelled `owner` as an authenticated user's stable id — the cart/order
endpoints sat behind `IsAuthenticated`, and the persistence layer keyed every cart on a
hard FK to the user. There was no notion of an anonymous shopper at all, so a visitor
had to sign in before they could even hold a cart.

Guest checkout is large and touches the money/inventory path, so it is being delivered
in three reviewable slices:

- **Slice A (this ADR):** the ownership foundation — let an anonymous guest own a cart,
  identified by a server-minted session cookie, with no UI change yet.
- **Slice B:** guest checkout proper — inline shipping + contact capture and guest order
  placement, and the storefront de-gating that lets a guest reach cart/checkout in the
  browser.
- **Slice C:** merging a guest's cart into their user cart when they sign in.

This ADR records only Slice A.

## Decision

### Owner is an opaque, prefixed string; the two owner kinds share one table
The application layer already keyed carts by an opaque `owner: str`. Slice A gives that
string a discriminating prefix produced at the HTTP boundary:

- an authenticated request owns by `u:<pk>` (the user's primary key);
- a guest owns by `g:<token>`, where `token` is a CSPRNG value.

`CartModel` keeps its user FK but makes it **nullable** and adds a nullable
`guest_token` column. A `CheckConstraint` (`cart_exactly_one_owner`) enforces that
exactly one of the two is set, and two **partial unique constraints**
(`uniq_cart_per_user_channel`, `uniq_cart_per_guest_channel`) preserve "one active cart
per owner per channel" for each owner kind — a plain `(owner, channel)` unique would
ignore guest rows, whose `owner` is `NULL`. This preserves referential integrity and
cascade-delete for real users (a cart still dies with its user) while giving guests a
first-class cart, and reuses the partial-unique-constraint idiom already established by
the address book (ADR 0031). `guest_token` is `NULL` (never `""`) when absent so the
constraints can distinguish "no guest owner" via `IS NULL`.

The prefix is the only coupling between the two outer layers: the interface **produces**
`u:`/`g:` ids (`src/interface/api/guest.py`), and the infrastructure **decodes** them
into column filters by splitting on `:` (`src/infrastructure/cart`). The domain and
application layers stay unaware — `owner` remains an opaque string — so the dependency
rule holds (infrastructure never imports the interface).

### The guest identity is a server-minted, HttpOnly cookie — the token is the credential
A guest's identity lives in a `guest_session` cookie the backend mints on the guest's
**first cart write** (`POST /cart/items/`). The token is a `secrets.token_urlsafe(32)`
value and the cookie carries the same posture as the auth cookies — HttpOnly (no JS
access), SameSite=Lax, Secure outside DEBUG. Because the token is unguessable and never
leaves an HttpOnly cookie, a guest can reach only their own cart, exactly as a user can
reach only theirs. There is still **no owner id in any URL**, so cross-owner access
(IDOR) stays structurally impossible for guests and users alike.

Because the token is a bearer credential, it must not leak into the *observability*
surface either. Everywhere an owner id is written to a structured log or the durable
audit trail, it passes through `src/application/shared/owner.py::safe_owner`, which
leaves a `u:<pk>` user id untouched but reduces a `g:<token>` owner to a
non-reversible fingerprint (`g:<sha256(token)[:12]>`). A guest stays correlatable
across log lines and audit rows, but the raw token lives only in the ownership column
that must match it (`cart.guest_token` / `order.guest_token`) — never in the logs.
(Added 2026-07-04, hardening the original slice; see `ISSUES.md`.)

Minting happens only on a write that will persist a cart. A **read** by a cookieless
visitor resolves to a throwaway owner that matches no row — it returns an empty cart and
sets **no** cookie, so a crawler or a first-time visitor is never tagged with a tracking
cookie. Updates and removes presuppose an existing cart, so a cookieless guest hitting
them resolves to that throwaway owner, finds no cart, and gets a 404 — again without a
cookie.

### The cart endpoints move to `AllowAny`
`CartView`, `CartItemsView`, and `CartItemDetailView` move from `IsAuthenticated` to
`AllowAny`; the owner is resolved per request via `resolve_owner`. Authenticated
requests are unaffected (they resolve to `u:<pk>` and never touch a guest cookie), and
the `401` responses those endpoints previously documented are dropped from the schema
since they can no longer occur.

### The order context is deliberately left alone in Slice A
Order placement still models `owner` as the bare user pk and reads a signed-in user's
cart by `owner_id`. A real user's cart is stored with `owner_id = <pk>` exactly as
before, so checkout still finds it; guest **orders** are Slice B. Keeping the order
context untouched keeps this slice small and the money path unchanged.

## Consequences
- A guest can build a per-channel cart with dynamic pricing, priced identically to a
  user's, without signing in — the backend foundation for guest checkout.
- The change is backwards-compatible for existing user carts: they already have
  `owner` set and `guest_token` `NULL`, satisfying the new constraints with no data
  migration.
- No UI changes yet: the storefront cart page still gates on login, so guests cannot
  reach the cart in the browser until Slice B de-gates it. Slice A is verified by unit +
  real-DB integration tests (guest isolation, cookie mint-on-write-only, user/guest and
  guest/guest separation, IDOR), and the existing browser E2E suite stays green.
- Guest carts are not reaped by a user cascade; a future cleanup job should expire guest
  carts past the cookie's max-age. Noted for a later slice, not built here.
