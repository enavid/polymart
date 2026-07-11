# ADR 0039 — Internal wallet + refund-to-wallet (idempotent store credit)

- Status: Accepted
- Date: 2026-07-06

## Context
The third Phase 4 slice adds an **internal wallet**: a per-user store-credit balance, and
the first thing that fills it — **refund-to-wallet**. When staff refund a captured payment,
the amount is returned to the shopper as internal credit rather than back to the gateway
(instant, no PSP round-trip, and a natural home for the rare "captured on a cancelled
order" case). The financial requirements mirror the rest of the phase: the credit must be
**atomic** with the payment's state change, **idempotent** (a repeated refund must never
double-credit), the balance must never lose an update under concurrency, and every movement
must be an auditable, exact `Decimal`.

## Decision

### A new `wallet` bounded context (full Clean Architecture)
Domain: a `Wallet` aggregate holding a single-currency `Money` balance (its own `Money`
value object — non-negative, fixed-point `Decimal`, never a float — copied, not imported,
per the bounded-context rule), and an append-only `WalletTransaction` ledger. `credit`
returns a new `Wallet` plus the `WalletTransaction` it produced (immutable, like `Payment`),
with `balance_after` captured on the entry so a statement renders without replaying the
ledger. `TransactionType` is the closed `credit`/`debit` vocabulary; this slice only ever
*credits* (a refund gives store credit) — debiting (pay-with-wallet) is a later slice.

Application: `WalletRepository` (owner-scoped reads; a row-locked `get_for_update`; a
`save_movement` that writes the balance and appends the ledger together; a
`find_transaction_by_source` idempotency probe), plus `CreditWallet` and `GetMyWallet`.

### Credit is idempotent by source reference, lazy, and row-locked
`CreditWallet` runs in one `UnitOfWork.atomic()`: if a ledger entry already exists for the
movement's `source_reference` (the payment reference), it returns that entry unchanged (a
repeated refund never double-credits); otherwise it locks the wallet row
(`select_for_update`), creating it lazily on first use, applies the domain `credit`,
persists the new balance + ledger entry together, and audits `wallet.credited` with the
before/after balance. A database `UniqueConstraint(wallet, source_reference)` (partial, so
null-source movements are unbounded) is the backstop: two concurrent refunds of the same
payment cannot both credit, independent of the application probe.

### Refund lives in the payment context and bridges to the wallet (like `PaidOrders`)
`RefundPayment` (payment application) is the orchestrator, mirroring how `CapturePayment`
bridges to the order context via `PaidOrders`. It locks the payment **by its public
reference** (`get_by_reference_for_update` — *not* owner-scoped: refund is a staff action,
gated at the transport), and: an already-`refunded` payment is returned unchanged
(idempotency); a non-`captured` payment is refused (`PaymentNotRefundableError` → 409); a
guest payment has no wallet to receive credit (`WalletOwnerRequiredError` → 409). Otherwise
it moves the payment `captured → refunded`, credits the shopper's wallet through a narrow
`WalletCredit` port (primitive-typed, so no wallet domain type crosses the seam), and audits
`payment.refunded` — all in one transaction, so any failure leaves the payment and wallet
untouched. The `WalletCreditAdapter` delegates to `CreditWallet`, whose nested `atomic()` is
a savepoint under the refund's transaction, so the two commit together and the refund
inherits the wallet's source-reference idempotency as a second guard.

### Transport
- `GET wallet/` — **authenticated-only** (a wallet always belongs to a registered user),
  owner resolved from the signed-in user (`u:<pk>`), never a client-supplied id, so one user
  can never read another's wallet. A user with no wallet yet reads an empty one (zero
  balance in the platform default currency, `WALLET_DEFAULT_CURRENCY=IRR`) rather than a 404.
- `POST payments/<reference>/refund/` — staff-only (`manage_orders`, reusing
  `OrderManagePermission`): refunds are an order-operations action. Amount is always the full
  captured amount taken from the payment, never client-supplied. 403 for a non-staff shopper,
  401 anonymous, 404 for an unknown/malformed reference.

### UI
A storefront **wallet page** (`/account/wallet`, linked from the account hub) shows the
balance and statement — the server's exact string, rendered (never recomputed) in Toman, RTL
with Jalali dates. A **staff refund control** on the order-detail payment block issues the
refund for a captured payment (shown only to staff, and only while captured); the payment
then reads `refunded` and the shopper's wallet is credited. Money on screen is always the
backend value, so there is a single source of truth.

## Consequences
- Refund-to-wallet is end-to-end and idempotent; store credit is a real, auditable ledger.
- Full-stack Playwright E2E covers the money flow (buy → pay online → capture → staff refund
  → wallet credited → refunded state), plus the shopper-cannot-refund (403) authorization
  boundary. `seed_e2e` now resets the wallet so the balance stays deterministic across runs.
- Deferred (see ROADMAP and `ISSUES.md`): **pay-with-wallet** (the `debit` flow), and two
  narrow, integrity-preserving concurrency edges that can surface a transient 500 (a
  concurrent first-credit racing the wallet's creation; a cross-currency refund into an
  existing single-currency wallet). Neither loses or duplicates money — the atomic
  transaction plus the unique constraints guarantee correctness — and both are retryable.
