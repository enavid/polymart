# ADR 0041 — Domain event bus (OrderPlaced / PaymentCaptured)

- Status: Accepted
- Date: 2026-07-06

## Context
Since Phase 3 the order and payment contexts have *announced* their money-moving facts only
two ways: a durable **audit** entry (the compliance record) and a **structured log** line (the
observability record). What was missing is a **publication seam** — a first-class way for a
use case to say "an order was placed" / "a payment was captured" and let *other* parts of the
system react (order-confirmation notifications, webhooks, fulfilment) without the use case
depending on any of them. The roadmap carried this over from Phase 3 ("the only deferred
Phase-3 item is event-bus publication") into Phase 4.

CLAUDE.md's target architecture names an **event bus + Celery for side effects**. This slice
delivers the *publication* half — the port, the typed events, the after-commit delivery, and
the two events wired in. Consumers (notifications, webhooks) are their own later phases; the
bus is the seam they attach to.

The financial constraint is **timing**: a side effect must never fire for a transaction that
rolled back. A confirmation email for an order that an oversell reverted, or a fulfilment
trigger for a capture that failed to commit, would be a real defect. So delivery must be tied
to the transaction outcome, not merely to the use case reaching a `publish` call.

## Decision

### A tiny shared-kernel event base, one event per context
`src/domain/shared/events.py` holds `DomainEvent` — an immutable (`frozen` dataclass) base with
`occurred_at` and a stable `name` (a dotted identifier such as `order.placed`). Each context
owns its own concrete events: `OrderPlaced` (`domain/order/events.py`) and `PaymentCaptured`
(`domain/payment/events.py`). Events are pure Python — no Django, no DRF.

An event carries everything a subscriber might need, **including** the money amount and the
owner id. But each event's `to_log()` projection is deliberately narrow: it returns only the
non-sensitive fields (order number, channel, currency, method, line count) and **never** the
amount or the raw owner — the same money-safe logging convention the use cases already follow
(a guest owner embeds a bearer token; a money value never belongs in the logs).

### The `EventPublisher` port; delivery is the adapter's concern
`src/application/shared/events.py` defines `EventPublisher.publish(event)` — the seam the use
cases depend on. The application layer makes **no promise about when** delivery happens; that
is an infrastructure decision, so the dependency rule keeps pointing inward.

`DjangoEventPublisher` (`infrastructure/events/publisher.py`) is an in-process bus that defers
delivery to `transaction.on_commit`. A use case publishes **inside** its `UnitOfWork.atomic()`
block, so:
- if the transaction **commits**, subscribers run (and the event is logged as
  `domain_event_published`, with `event_name` distinct from structlog's own `event` key);
- if it **rolls back**, the callback is discarded and **no** subscriber runs;
- outside any transaction, `on_commit` fires immediately, so a publish is never silently lost.

Subscribers are plain callables registered at the composition root. There are **none yet** —
this slice ships the publication seam; notification/webhook/fulfilment handlers register in
their own phases without any use case changing.

### Wiring: publish where money-relevant state is created
- `PlaceOrder` and `CreateManualOrder` publish `OrderPlaced` (a manual order is a real placed
  order) right after the audit write, still inside the transaction.
- `CapturePayment` (online callback) and `PayWithWallet` publish `PaymentCaptured` at the
  moment of capture. Because `CapturePayment` is **idempotent** — a duplicate callback returns
  before `_settle_captured` — `PaymentCaptured` is published **exactly once** per real capture,
  never on a repeated callback. `CapturePayment` gains a `Clock` so the event's `occurred_at`
  is the capture instant (mirroring `PayWithWallet`, which already had one).

Publishing inside the transaction (rather than after the `with` block) is what lets the
adapter's after-commit machinery discard the event on rollback: the `on_commit` registration
is itself part of the transaction.

## Consequences
- The platform now has a real publication seam: typed domain events flow through one port, and
  future side effects subscribe at the composition root without touching the domain or use
  cases. This is the `OrderPlaced`/`PaymentCaptured` publication the roadmap deferred from
  Phase 3.
- Delivery is **after-commit**, proven by an integration test driving real Django transactions
  (`transaction=True`): the subscriber sees the event only post-commit, a rollback delivers
  nothing, and a publish outside a transaction fires immediately.
- Observability without leakage: every delivered event is logged via its own `to_log()`, which
  excludes the amount and the raw owner — the existing money-safe convention.
- Backend-only slice: no UI surface and no new user-facing behaviour, so no new E2E. The
  existing checkout / online-payment / wallet E2E already drive the code paths that now
  publish, and the audit + structured-log records they assert are unchanged.
- Deferred (see ROADMAP): actual **consumers** (notifications, webhooks, fulfilment) are later
  phases; a `payment.refunded` event was intentionally left out of scope (only
  `OrderPlaced`/`PaymentCaptured` were named). A subscriber that raises would surface after
  commit; the contract documents that subscribers must not raise, and isolation can be added
  when the first real subscriber lands.
