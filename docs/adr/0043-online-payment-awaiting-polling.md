# ADR 0043 — Online payment "awaiting confirmation" polling on the order page

- Status: Accepted
- Date: 2026-07-07

## Context
The online gateway (ADR 0038) settles a payment out-of-band: the buyer returns from the PSP
to the callback, which hands settlement to the idempotent `capture_online_payment` Celery
task. In dev/test that task runs **eager** (synchronous), so by the time the browser lands on
the order page the payment is already `captured`. In **production** the task runs on an async
worker, so there is a real window where the buyer is back on the order page but the payment is
still `pending` — waiting for the webhook/task to capture it. Until now the order page rendered
that transient `pending` online payment as a plain, static status with no indication that
settlement was still in flight, and no way to see the result without a manual reload.

This slice closes that gap on the client. It is deliberately **frontend-only**: the server
already exposes the authoritative payment state via `GET payments/for-order/<n>/`; nothing new
is needed server-side, and no new money movement is introduced.

## Decision

### A bounded auto-poll while an online payment is settling
The order page's payment section auto-refreshes only while the payment is an **online** one
that is still **pending** (`isSettlingOnline`). Polling is:

- **Bounded** — `refetchInterval` returns `ONLINE_POLL_INTERVAL_MS` (2s) only while settling
  *and* `pollAttempts < ONLINE_POLL_MAX_ATTEMPTS` (10); otherwise `false`. A `useEffect` ticks
  the attempt counter once per completed read (`query.dataUpdatedAt`). So the page polls for at
  most ~20s and never spins forever on a genuinely stuck or abandoned payment.
- **Self-terminating** — the moment the read returns a settled payment (`captured`/`failed`),
  `isSettlingOnline` is false, `refetchInterval` returns `false`, the banner disappears, and
  the final status renders. No client-side inference of the outcome — the status text is always
  the server's.
- **Recoverable** — when the bounded polling is exhausted, the banner stops and offers a manual
  "check again" button (`recheck` resets the counter and refetches), rather than leaving the
  buyer stuck.

### The banner
`OnlineAwaitingBanner` renders inside the payment card while settling: a live spinner +
"confirming your payment" note (`role="status" aria-live="polite"` for assistive tech) while
polling, switching to the exhausted note + re-check button once the attempts run out. It is
shown only for a settling online payment — never for COD, card-to-card, or an
already-captured/failed online payment.

## Consequences
- The production async-capture window now has a first-class UI: the buyer sees that settlement
  is in progress and the page resolves itself to paid/failed without a manual reload, with a
  bounded, recoverable fallback if the webhook never arrives.
- **Testing**: covered by React component tests (Vitest + MSW) — the banner shows for a
  settling online payment; polling stops and the banner clears once the payment settles; the
  banner is absent for a captured online payment and for a pending COD payment. It is **not**
  covered by a new Playwright E2E: under eager Celery (dev/test) online capture is synchronous,
  so the payment is already `captured` on arrival and the settling state is never observable
  end-to-end — the async window only exists in production. The existing online-payment E2E
  (pay-at-gateway-capturing / gateway-cancel-fails, ADR 0038) was re-run and stays green,
  confirming the PaymentSection rewrite did not regress the eager-capture happy path.
- **Deliberate scope**: this is client-side polling of the existing read endpoint, not a
  server-push or long-poll. A dedicated "awaiting webhook" result page/route, or server-sent
  events, remains a possible future refinement; the bounded poll on the order page covers the
  common case without new backend surface.
