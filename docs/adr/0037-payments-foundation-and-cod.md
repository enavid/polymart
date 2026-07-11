# ADR 0037 — Payments foundation and cash on delivery (COD)

- Status: Accepted
- Date: 2026-07-05

## Context
Phase 4 opens the payments phase. The whole phase turns on **abstracting the gateway** —
Iran uses Shaparak/PSP providers (Zarinpal, Zibal, …), never Stripe/PayPal, and a provider
must be a swappable adapter, not a core dependency. Rather than start with an external
redirect/webhook gateway, this first slice lays the **foundation** every later payment
method plugs into — a `Payment` bounded context, a `PaymentStatus` state machine, and the
`PaymentGateway` port/registry seam — and delivers the first end-to-end method, **cash on
delivery (COD)**, which needs no external system. Online gateways (authorize/capture/void,
redirect/callback, idempotent webhooks), the internal wallet, and card-to-card follow in
later slices.

## Decision

### A new `payment` bounded context (full Clean Architecture)
`domain/payment` (pure Python), `application/payment` (use cases + ports),
`infrastructure/payment` (ORM, adapters), `interface/api/payment` (DRF). The domain owns
its own `Money` and `OrderRef` value objects rather than importing the order context's
types (the bounded-context rule — neighbours are coupled only through narrow references),
exactly as the order context copies `Sku`/`Money` from the cart.

### The `Payment` aggregate and its state machine
`Payment` captures the amount owed at initiation (a snapshot of the order total, so a later
catalog price change never rewrites what was charged), the chosen `PaymentMethod`, the
owner (`u:<pk>`/`g:<token>`), and an opaque, unguessable public `PaymentReference`. It moves
through a declared state machine held as data (mirroring the order aggregate):

```
pending    -> {authorized, captured, failed, cancelled}
authorized -> {captured, voided, failed}
captured   -> {refunded}
failed / cancelled / voided / refunded  (terminal)
```

The full machine is delivered and unit-tested now because the slice's scope names it and
it is the aggregate's defining behaviour; the use cases that *drive* the later transitions
(capture on an online callback, void, refund to wallet) arrive with their own slices. COD
creates a `pending` payment and — correctly — moves no money at checkout: the cash is
collected by the courier on hand-over, which is the operations phase (capture-on-delivery),
so no transition happens here.

### The gateway port/registry — the pluggable seam
`PaymentGateway` is an ABC with `method` and `start(intent) -> PaymentStartResult`. A
`PaymentGatewayRegistry` resolves a method to its registered adapter and raises
`UnsupportedPaymentMethodError` for a method with no adapter. This is the extension point
the phase is built around: a new method (an online Zarinpal adapter, card-to-card) is
**registered at the composition root** without touching the domain or the use case. This
slice registers exactly one adapter, `CashOnDeliveryGateway`, whose `start` reports
`next_action = none` (nothing more for the shopper to do). `online`/`card_to_card` are
recognised `PaymentMethod` values with **no** registered adapter yet, so choosing them is a
clean 400 (`unsupported`), distinct from an unknown method (rejected by the serializer).

### Initiation is owner-scoped, amount-from-server, atomic, idempotent-guarded
`InitiatePayment` resolves the order through a narrow, **owner-scoped** `OrderReader`
(`get_payable`): an order that is not the caller's — or does not exist — is indistinguishable
(`PaymentOrderNotFoundError` → 404), so payment never reveals whether another shopper's
order exists (IDOR-safe for users and guests alike). The order must be **payable** (still
`pending`; an already-paid/cancelled/fulfilled order is a 409 `OrderNotPayableError` — the
caller's own order, so surfacing its state is not a leak). The amount is captured from the
order's server total, so a client can never charge itself a chosen figure. Everything —
the payability re-check, the double-initiation guard, the gateway `start`, the persist, and
the money-relevant audit (`payment.initiated`) — runs inside one `UnitOfWork.atomic()`, so
any failure leaves no payment and no trail.

An order holds **at most one active payment** (pending/authorized/captured). This is
guarded in the use case *and* enforced by a Postgres **partial unique constraint**
(`unique(order_number) where status in (active)`), so two concurrent initiations cannot both
create one (the second `IntegrityError` is translated to `PaymentAlreadyExistsError` → 409),
independent of the application guard. A spent payment (failed/cancelled/voided) frees the
order for a fresh attempt.

### Endpoints (owner-scoped, guest + user, no owner id in the URL)
All `AllowAny`, resolving the owner from the request (a user's cookie-JWT or a guest's
HttpOnly session cookie), never a client-supplied id — matching the cart/order posture:
`POST /payments/` (initiate), `GET /payments/for-order/<number>/` (the order's payment),
`GET /payments/<reference>/` (by reference). The `for-order/` route is declared before the
`<reference>` route so it is never read as a reference. Money is a string in every response
(the exact `Decimal`). No new RBAC permission: paying for one's own order is self-service,
owner-scoped, exactly like placing it. Payments never mint a guest cookie — a guest reaching
payment already holds one from building their cart and placing their order.

### Checkout chooses the method; the order confirmation shows the payment
Checkout is two bounded contexts, so the UI places the order then initiates the chosen
payment against it (two sequential calls; for COD the second simply records "pay on
delivery"). The review step offers a **payment-method chooser** — COD selected by default,
`online`/`card_to_card` shown but disabled ("coming soon") so the roadmap is visible without
offering a path the backend would reject. The order-detail page reads the order's payment
(`getPaymentForOrder`) and shows a **payment block** (method + status); an order without a
payment yet (a 404) renders a muted "no payment" note, not an error. The amount is not
repeated in the block — it is the order total shown below — so money has a single source of
truth on the page. Payment method/status render through localized labels (RTL/Persian).

## Consequences
- The port/adapter seam the whole phase needs exists; adding the online gateway (and
  card-to-card, and the wallet as a payment source) is registering an adapter, not
  reworking the domain. The COD method is fully working end to end for users and guests.
- The `Payment` state machine and money value object are in place (Decimal-only, never
  float), and the "one active payment per order" invariant is guaranteed at the database.
- Verified by unit tests (the aggregate + state machine, value objects, the registry, and
  `InitiatePayment` — capture-from-order-total, gateway resolution, owner-scoping, payability,
  double-initiation guard, audit, atomic rollback, and the owner-scoped reads), real-DB
  integration tests (the repository round-trip + owner-scoping + the partial-unique
  constraint + the order reader; the endpoints incl. COD initiation, reads, double-initiation
  409, unsupported-method 400, non-pending 409, and payment IDOR 404 for users and guests),
  frontend tests (the typed client; the checkout method chooser + COD initiation; the
  order-detail payment block + its 404/none state), and full-stack Playwright specs (a
  signed-in shopper and a guest both check out with COD and see the payment block; the
  method chooser shows COD selectable with the others disabled; the API rejects an
  unsupported method (400) and refuses to read another account's payment (404)).
- **Deferred to later Phase-4 slices** (unchanged scope): the online Iranian gateway
  (authorize/capture/void, redirect/callback, idempotent Celery webhooks), the internal
  wallet + refund-to-wallet, card-to-card, and the `OrderPlaced`/`PaymentCaptured`
  event-bus publication carried over from Phase 3. Capturing a COD payment on delivery
  belongs to the operations phase.
