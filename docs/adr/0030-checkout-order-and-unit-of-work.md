# ADR 0030 — Checkout → Order placement, the Unit of Work, and the order state machine

- Status: Accepted
- Date: 2026-07-02

## Context
Phase 3 delivered the persistent cart (ADR 0027) and the storefront variant/price
read (ADR 0028). The next slice is the money- and inventory-critical step the whole
project has been building toward: turning a cart into a **placed order**. Three things
were deliberately deferred to here:

1. the **checkout interactor** that converts a cart into an order;
2. the **Unit of Work** — the multi-aggregate transaction boundary repeatedly deferred
   from Phase 1/3 (atomic OTP counter, transactional money/inventory audit) and from
   the catalog's stock work;
3. the **order state machine** (Sylius-style order/payment/fulfilment states).

Because placing an order moves real inventory and captures real money, this slice is
held to the standard of a financial feature: exact `Decimal` money, atomic
all-or-nothing writes, anti-overselling under concurrency, transactional audit, and
strict owner-scoping (no IDOR).

## Decision

### A new `order` bounded context, Clean-Architecture all the way down
- **Domain** (`domain/order`): its own value objects (`Money` — `Decimal`, never
  `float`; `Sku`; `OrderQuantity`; `ChannelRef`; `OrderNumber`; `OrderStatus`), the
  `OrderLine` and `Order` aggregate, and the domain services that assemble lines and
  the total. Like the cart, the context owns its own `Money`/`Sku` rather than
  importing the catalog's or cart's — a bounded context depends only on narrow
  abstractions of its neighbours, never their domain types.
- **Application** (`application/order`): the ports and the four use cases
  (`PlaceOrder`, `ListMyOrders`, `GetMyOrder`, `CancelMyOrder`).
- **Infrastructure** (`infrastructure/order`): the ORM models, mappers, repository,
  the narrow adapters bridging to cart/catalog/channel, the order-number generator,
  the clock, and the Unit of Work.
- **Interface** (`interface/api/order`): thin DRF views over `orders/`.

### Prices are captured, not referenced
An `OrderLine` stores the `unit_price` and `line_total` that were in force at
placement. The aggregate enforces two invariants: every line is in the order's
currency, and the stated total equals the sum of the line totals. A later catalog price
change therefore never rewrites history — the order is self-describing. (The cart, by
contrast, is priced *dynamically* at read time; ADR 0027.)

### The Unit of Work is the transaction boundary
`UnitOfWork.atomic()` is a context manager; the Django adapter is
`transaction.atomic()`. `PlaceOrder` runs its entire body inside it: read the cart,
capture each line's price, **deduct stock**, build and persist the order, clear the
cart, and **write the audit entry** — all commit together or roll back together. This
is the long-deferred **transactional audit** for a money/inventory path: the
`order.placed` entry shares the order's transaction, so the trail can never record a
purchase that did not commit.

### Anti-overselling reuses the catalog's locked stock repository
The `Inventory` adapter delegates to the catalog's `adjust_quantity`, which takes a
`select_for_update` row lock and refuses to drop below zero. Because deductions happen
inside the checkout Unit of Work, an oversell on a *later* line rolls back the
deductions already made on *earlier* lines — no partial capture, no order, cart intact.
This is verified end-to-end (`test_place_order_integration.py`) with a two-line cart
whose second line oversells.

### The order state machine
`OrderStatus` is `pending → {paid, cancelled}`, `paid → {fulfilled, cancelled}`, with
`fulfilled`/`cancelled` terminal. Transitions are a single declarative table on the
(immutable) aggregate; an illegal transition raises. Checkout lands an order in
`pending`. `CancelMyOrder` exercises the machine now: a shopper may cancel their own
*pending* order, which returns the captured stock and audits `order.cancelled`, again
inside one Unit of Work. Cancelling a `paid` order (which needs a refund) and the
`paid`/`fulfilled` transitions themselves are driven by the payments/operations phases.

### Owner-scoping makes IDOR structurally impossible
There is no owner id in any request body and no sequential id in any URL. The order
`number` is an opaque, unguessable reference (`ORD-` + 12 chars of CSPRNG randomness),
and every repository read is scoped to the authenticated owner. A shopper can only ever
place, read, or cancel their own orders; another user (or an anonymous one) gets a
`404`, never a leak of existence. Verified in both the API tests and the browser E2E.

### HTTP surface (all behind `IsAuthenticated`)
- `POST /orders/` — checkout: `201` with the placed order; `409` for an empty cart,
  an oversell, or a line that lost its price; `400` for an unknown channel.
- `GET /orders/` — the caller's own order history (paged, newest first).
- `GET /orders/<number>/` — one of the caller's orders; `404` otherwise.
- `POST /orders/<number>/cancel/` — cancel a pending order; `409` if not cancellable.

Money crosses the wire as an exact string so the `Decimal` survives JSON; the storefront
renders that string and never recomputes a total.

### Storefront UI
A **checkout** action on the cart (disabled while any line is unavailable), an **order
confirmation / detail** page with a **status timeline** and an inline (no native-dialog)
**cancel**, and a **my-orders** history list, all on the typed API client with Persian
RTL and Jalali dates.

## Consequences
- **Positive.** The core purchase path exists end-to-end and is atomic, audited, and
  oversell-proof. The Unit of Work and transactional audit — deferred since Phase 1 —
  are now real and reusable by future money paths (payments, refunds). Coverage stays
  ~100% on the new domain/use-case code; the decisive atomicity and IDOR properties are
  covered by integration and browser tests.
- **Negative / deferred.** No guest checkout, address book, or manual order yet (their
  own Phase 3 bullets). No event bus (`OrderPlaced` is audited + logged, not published)
  — that lands with payments/fulfilment. Payment capture and the `paid`/`fulfilled`
  transitions are Phase 4/6. Order history paging is limit/offset (cursor later).
- **Migration.** `order/0001_initial` adds `order_order` and `order_order_line`.
- **PII.** Structured logs carry the order number, line count, and currency but never
  the amount (a money value) or any phone/email; the captured totals live only on the
  audit entry (JSON scalars), and the actor is the stable user id.
