# ADR 0027 — Cart: persistent cart aggregate and dynamic pricing

- Status: Accepted
- Date: 2026-07-01

## Context
Phase 3 opens the money-critical path (cart → checkout → order). This first slice
adds the **persistent cart**: a shopper's per-channel list of intended purchases,
with add / update / remove and a **priced projection** (line totals and a cart
total). It is a new bounded context (`cart`), the first outside the catalog since
Phase 1.

Two shaping decisions were taken with the maintainer before implementation:

1. **Dynamic pricing** (not a captured snapshot). A cart line persists only `(sku,
   quantity)`; the unit price and totals are computed **at read time** from the
   variant's *current* per-channel price. Price capture happens later, at order
   creation (a future slice), where a frozen price is the correct model. Until
   then a cart always reflects today's price.
2. **Scope**: the backend cart API, the storefront variant/price read it needs
   (ADR 0028), and the cart UI — delivered together so the flow is testable in the
   browser.

No money or inventory *moves* in a cart (that begins at order placement), so this
slice deliberately does **not** write to the audit trail; it emits structured logs
only. The Unit of Work and the transactional money/inventory audit deferred from
Phases 1 and 3 belong to the checkout/order slice, not here.

## Decision
- `domain/cart/` — a pure aggregate, mirroring the catalog's value-object rigour but
  owning its **own** `Money` and `Sku` rather than importing the catalog's (a
  bounded context depends on abstractions of its neighbours, never their domain
  types). The one deliberate difference from the catalog's `Money`: a cart amount is
  **non-negative** (an empty cart totals zero) whereas a catalog base price is
  strictly positive.
  - Value objects: `Sku` (upper-cased kebab, same shape the catalog canonicalises
    to, so a reference never fails purely on casing), `CartQuantity` (a **positive**
    integer, bounded; `bool` rejected — zero is not a quantity, removing a line is an
    explicit op), `ChannelRef`, and `Money` (fixed-point `Decimal`, never a float;
    non-negative, finite, ≤18 digits/4 places; `times`/`add` are exact and
    currency-checked).
  - `Cart` entity: an owner + channel + ordered lines, with the invariant that a
    variant appears at most once (adding again increments; enforced on mutation *and*
    on rebuild-from-storage). `add_item` / `set_item` / `remove_item` hold the
    structural rules; `set`/`remove` on a missing line raise `CartLineNotFoundError`.
    These mutations are applied to a **locked** aggregate inside the repository (see
    below), so a cart read-modify-write cannot lose an update under concurrency.
  - `price_cart` domain service: given the cart and a per-SKU map of current unit
    prices, it computes each line total and the cart total with exact `Decimal`
    maths. A line whose variant has **no price in the channel** (it became
    unpurchasable after being added) is kept visible but marked `available = False`
    and **excluded from the total**, so an unpriceable line never silently inflates
    or invalidates it. A price in the wrong currency is refused, not summed.
- `application/cart/` — three narrow ports and four use cases (constructor-injected):
  - Ports: `CartRepository` (`get` — read-only, never fails, returns an empty cart
    for a first read; `apply(owner, channel, mutate)` — a unit-of-work method that
    loads the cart, applies the domain mutation, and persists, **all under one row
    lock** so the whole read-modify-write is serialized), `VariantPricingReader`
    (`exists` + `price_of(sku, channel)`, a narrow read onto the catalog), and
    `ChannelReader` (`currency_of`, a narrow read onto the channel context).
  - `AddCartItem` checks the variant **exists** (404) and is **purchasable in the
    channel** — has a price (400) — before persisting, so a stored line is always
    purchasable at add time. `UpdateCartItem` sets an absolute quantity (404 on a
    missing line). `RemoveCartItem` removes one (404 on a missing line). `GetCart`
    reads and prices. All resolve the channel currency first (unknown channel → 400)
    and return the priced projection. Logs name the actor (the stable user id) and
    **never** carry a price/amount (money-sensitive values stay out of the logs).
- `infrastructure/cart/` — `CartModel` (`unique(owner, channel_slug)`; the owner is a
  hard FK to the user, the channel a soft slug reference matching how the catalog
  references channels) and `CartLineModel` (`unique(cart, sku)`, ordered by
  position). `DjangoCartRepository.apply` runs under `transaction.atomic()` +
  `select_for_update()` on the cart row: it locks, loads the cart, applies the domain
  mutation to the locked snapshot, then replaces the line set. Two concurrent
  mutations for the same `(owner, channel)` **serialize** instead of both reading the
  same pre-state and losing an update (or interleaving the clear+reinsert into a
  unique-constraint error); a mutation that raises rolls the whole thing back.
  `DjangoVariantPricingReader` / `DjangoChannelReader`
  bridge to the catalog and channel models and rebuild a cart-domain `Money` (never a
  float). Migration `cart/0001`.
- `interface/api/cart/` — `IsAuthenticated` endpoints. The cart is **always resolved
  from `request.user.pk`**, never from a client-supplied id; there is **no cart id in
  the URL space**, which makes cross-user access (IDOR) structurally impossible. Money
  is projected as an **exact string** (an unavailable line's prices as `null`).
  - `GET /api/v1/cart/?channel=<slug>` — read the priced cart.
  - `POST /api/v1/cart/items/` — `{channel, sku, quantity}` add/increment.
  - `PUT /api/v1/cart/items/<sku>/` — `{channel, quantity}` set absolute quantity.
  - `DELETE /api/v1/cart/items/<sku>/?channel=<slug>` — remove a line.

## Consequences
- A cart is honest about the present: an item whose price changed or was withdrawn
  is re-priced (or shown unavailable) on the next read, with no stale snapshot to
  reconcile. The trade-off — a price seen in the cart is not *promised* until
  checkout captures it — is the correct model for a pre-order cart and is made
  explicit by the frozen-price capture that the order slice will add.
- The three reader ports keep the cart independent of the catalog and channel
  domains; the catalog/channel can evolve without reshaping the cart.
- No audit here is intentional and documented: nothing of monetary/inventory record
  moves until order placement, which is where the transactional audit (and Unit of
  Work) deferred from earlier phases will live.
- Coverage 100% (domain, application, infrastructure, interface).
