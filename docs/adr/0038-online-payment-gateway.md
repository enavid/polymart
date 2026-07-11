# ADR 0038 — Online payment gateway (redirect + verify/capture, idempotent callback)

- Status: Accepted
- Date: 2026-07-06

## Context
The second Phase 4 slice delivers the marquee item: a real **online Iranian gateway**,
plugged into the payment foundation from ADR 0037. The flow is the redirect model every
Iranian PSP uses (Zarinpal/Zibal/Shaparak): request a payment, send the shopper to the
gateway's hosted page, and on their return **verify** with the gateway server-side (which
is the actual capture of funds). The two hard requirements are the financial ones — the
callback must be **idempotent** (a duplicate return, or a retry, must never double-capture
or double-pay the order) and the capture must be **atomic** with marking the order paid.

## Decision

### An online gateway is a verifiable gateway (ISP)
`OnlinePaymentGateway` extends the base `PaymentGateway` with one method, `verify(...)`.
COD implements only `start`; an online gateway adds `verify` — the server-side confirmation
that captures the funds. The capture use case requires this capability, so a method whose
gateway cannot verify cannot be captured. `PaymentStartResult` gained a `gateway_reference`
(the provider's "authority"/token), recorded on the `Payment` at initiation (a new
`gateway_reference` column, unique when present) so the callback can resolve exactly one
payment.

### Zarinpal adapter behind an HTTP port; a DEBUG mock for offline E2E
`ZarinpalGateway` implements request + verify against a narrow `HttpTransport` port (a
stdlib, https-only JSON POST), so it is unit-tested with a fake transport — no live network
— and the HTTP client stays an infrastructure detail. Because there is no real PSP in
dev/E2E, a `MockOnlineGateway` (guarded by `PAYMENT_ONLINE_MOCK`, defaulting to `DEBUG`,
exactly like the OTP dev SMS sender) emulates the redirect→callback flow offline: `start`
points the shopper at a backend-served "Pay/Cancel" page, and `verify` confirms capture.
The composition root picks the mock in dev/test and the real Zarinpal in production;
`card_to_card` remains a recognised method with no adapter (400).

### Capture is idempotent, atomic, and never trusts the redirect
`CapturePayment` locks the payment by its `gateway_reference` (`select_for_update`), so
concurrent callbacks serialize. An already-settled payment is returned unchanged (a
duplicate callback is a no-op — the core idempotency guarantee). A cancelled callback fails
a still-open payment **without** verifying. A successful callback **re-verifies with the
gateway** — the browser redirect can be spoofed, so the server confirmation is the only
source of truth for whether money moved — and, on capture, moves the payment to `captured`,
marks the order `paid` (through the order's own state machine, via the narrow `PaidOrders`
bridge, locked and idempotent), and audits `payment.captured` — all in one transaction, so
a failure anywhere leaves the payment and order untouched. A failed verify (or NOK) fails
the payment and frees the order for a fresh attempt.

### The callback is the webhook; capture runs on Celery
`GET /payments/callback/` receives the authority + status, resolves the order to return the
shopper to, hands settlement to the idempotent Celery task `capture_online_payment`, and
302-redirects the browser to the order page. Celery runs **eager in dev/test** (the capture
completes inline, so the result is immediately visible and the E2E is deterministic without
a worker) and **async with a real worker in production**. The task is defensive: an
unresolvable reference, or an order that was cancelled between initiation and the callback
(so it can no longer be marked paid — the whole capture rolls back), is logged and swallowed
rather than crashing the worker; such a stuck case leaves the payment un-captured for
reconciliation rather than paying a cancelled order.

### UI: choose online, redirect, and return
The checkout method chooser enables **online** (card-to-card stays "coming soon"). On
placement the frontend initiates the payment and, on `next_action: "redirect"`, hands the
browser to the gateway URL (`window.location.assign`); COD still routes straight to the
order confirmation. After the gateway callback the shopper lands back on the order page,
which shows the order status (paid) and the payment block (method + captured/failed). Money
is the exact server string throughout; the mock gateway page escapes/quotes the echoed
authority (it cannot be turned into an XSS vector) and is inert unless the mock is wired.

## Consequences
- The core Phase 4 goal is met: a real Iranian gateway (Zarinpal) is wired behind the
  pluggable seam, with an offline mock making the whole redirect→callback→capture→order-paid
  flow deterministically testable end to end. Adding another PSP is one more adapter.
- Capture is idempotent (row-locked, no-op on a settled payment; DB partial-unique still
  guards one active payment per order) and atomic (capture + order-paid + audit in one
  transaction), and never trusts the client redirect (always re-verifies server-side).
- Verified by unit tests (the aggregate capture/fail + gateway-reference rules; the Zarinpal
  adapter's request/verify mapping incl. the idempotent "already verified" code 101, against
  a fake transport; the mock gateway; the HTTP transport; `CapturePayment` — success,
  idempotent repeat, cancel-without-verify, failed-verify, terminal no-op, not-found,
  non-online gateway; the container's mock-vs-Zarinpal wiring), real-DB integration tests
  (the `gateway_reference` round-trip, the locked/unlocked lookups, `update_status`, the
  `PaidOrders` bridge incl. idempotent + illegal-transition; the full callback flow —
  capture→order paid, idempotent repeat, NOK→failed→order pending, failed-attempt-then-retry,
  unknown/missing authority, the mock page, guest online payment; the task's error
  swallowing incl. the cancelled-order rollback), frontend tests (the online redirect vs the
  COD push), and full-stack Playwright specs (pay online at the mock gateway → order
  captured/paid; cancel at the gateway → payment failed, order stays pending → cancel to
  restock).
- **Deferred (next Phase-4 slices):** an "awaiting webhook / pending" polling result page
  (today dev/test capture is synchronous, so the order page shows the settled state at
  once); a refund flow for the rare capture-on-cancelled-order stuck case (needs the wallet
  slice); the internal wallet + refund-to-wallet; card-to-card; and the
  `OrderPlaced`/`PaymentCaptured` event-bus publication carried over from Phase 3.
