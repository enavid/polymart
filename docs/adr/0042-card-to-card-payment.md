# ADR 0042 — Card-to-card payment (manual bank transfer, staff-verified)

- Status: Accepted
- Date: 2026-07-06

## Context
`card_to_card` has been a recognised `PaymentMethod` with no adapter since the payments
foundation (ADR 0037) — initiating it returned 400. This slice makes it real. In Iran,
card-to-card (کارت‌به‌کارت) is a **manual** flow: the buyer transfers money from their bank
card to the merchant's card via their banking app, then reports the transfer's tracking
reference; a human on the merchant side checks the money arrived and confirms it. There is no
automated gateway and no synchronous capture — settlement is **asynchronous and
staff-verified**. The financial constraints are the phase's usual: the confirm must be atomic
with the order becoming paid, idempotent under concurrency, the amount must be the server's
captured order total (never client-supplied), and every movement auditable.

## Decision

### The flow: buyer initiates → buyer reports transfer → staff confirm/reject
1. **Initiate** — `card_to_card` is now registered in the `PaymentGatewayRegistry`. Its
   `CardToCardGateway.start` moves no money and issues no redirect (`next_action: none`, like
   COD): the payment is created `pending`, awaiting an out-of-band transfer.
2. **Report** — the buyer submits their bank tracking reference. `SubmitCardToCardReference`
   (owner-scoped, row-locked) attaches it to the still-pending payment, once, and audits
   `payment.transfer_submitted`. The reference is the buyer's *claim*, not proof.
3. **Confirm / reject** — staff verify the transfer arrived, then either
   `ConfirmCardToCardPayment` (captures the payment, marks the order paid, announces
   `PaymentCaptured`, audits `payment.captured`) or `RejectCardToCardPayment` (fails it, audits
   `payment.rejected`, freeing the order for a fresh attempt). Both are **staff** actions gated
   by `manage_orders`, addressed by the payment's public reference, row-locked, and
   **idempotent** (a repeat confirm/reject on an already-settled payment is a no-op).

Confirm **refuses a payment with no submitted transfer reference** (409): staff must have
something to verify, so a card-to-card payment can never be captured on nothing.

### One new aggregate field, captured like every other snapshot
`Payment` gains `transfer_reference: str | None` (NULL for every other method and until the
buyer submits) plus `with_transfer_reference` (set-once). It rides the state machine
unchanged. A new nullable column + migration; the mapper round-trips it.

### The destination card is per-channel config, resolved by the order's channel
The merchant's receiving card is **sensitive banking configuration**, so it lives with the
other payment-gateway settings (like the Zarinpal merchant id) rather than a public model or
API — `PAYMENT_CARD_TO_CARD = {"<channel-slug>": {"number": ..., "holder": ...}}`, **keyed by
channel** so each channel collects on its own card. A `CardToCardDirectory` port
(`SettingsCardToCardDirectory` adapter) resolves it; `PayableOrder` gained `channel` so the
order's channel selects the card. `GetCardToCardInstructions` (owner-scoped) serves it to the
buyer — never entered client-side, an unconfigured/partial channel is a clean 409.

### Transport
Initiation stays `POST payments/` (dispatched by method). New routes: owner-scoped
`GET payments/for-order/<n>/card-to-card/` (destination card) and
`POST payments/for-order/<n>/transfer-reference/` (report); staff
`POST payments/<ref>/confirm/` and `POST payments/<ref>/reject/` (manage_orders → 403 for
non-staff). The payment projection now carries `transfer_reference`.

### UI
Checkout enables card-to-card. On the order page, a pending card-to-card payment shows the
server-owned destination card and a one-time form to report the transfer reference; once
reported it shows the reference and an "awaiting confirmation" note. Staff see confirm/reject
controls (confirm disabled until a reference is reported). All money/card text is the server's
exact string, never recomputed. Numbers render `dir="ltr"`.

## Consequences
- Card-to-card is a real, end-to-end method: buyer reports → staff verify → order paid, all
  atomic, idempotent, owner-scoped, and auditable. Covers the last unchecked Phase-4 method.
- `PaymentCaptured` (ADR 0041) fires on a staff confirm exactly as it does for online/wallet
  capture — one capture path's worth of side effects, once.
- Tests: unit (the four use cases against fakes — owner-scoping, once-only submit, idempotent
  confirm/reject, the no-transfer-reference refusal), real-DB integration (the full flow, the
  403/404/409 boundaries, misconfigured-channel via `override_settings`), frontend component
  tests, and a full-stack Playwright E2E (buyer reports → shopper-cannot-confirm 403 → staff
  confirm → order paid). ~100% coverage on the new code.
- **Deliberate scope**: staff confirm/reject live on the owner-scoped order page and the API
  (as the E2E drives it), mirroring how refund works today — there is **no dedicated staff
  "pending card-to-card" review queue** yet. That queue (a staff-only list endpoint + admin
  page) is a natural follow-up, tracked alongside the same enhancement for refunds.
- **Configuration**: the destination card is per-channel *settings*, honouring "per-channel"
  while keeping merchant banking detail out of any public surface. Moving it into a
  channel-admin screen (with object-level permissions) is a future option.
