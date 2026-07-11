# ADR 0040 — Pay-with-wallet (spend store credit at checkout)

- Status: Accepted
- Date: 2026-07-06

## Context
The wallet slice (ADR 0039) gave shoppers a store-credit balance and the first thing that
fills it (refund-to-wallet). This slice closes the loop: **spending** that balance. A
signed-in shopper can pay for an order from their wallet at checkout — a new `wallet` payment
method that settles **synchronously and internally**, with no gateway round-trip. The
financial requirements are the phase's usual: the debit must be **atomic** with the payment's
capture and the order becoming paid, the balance must never go into overdraft or lose an
update under concurrency, the amount must be the server's captured order total (never
client-supplied), and every movement must be an auditable, exact `Decimal`.

## Decision

### The wallet learns to debit (mirror of credit)
Domain: `Wallet.debit` removes a positive, same-currency amount, refusing an uncovered spend
with `InsufficientWalletFundsError` **before** producing any movement (a wallet never goes
negative). `Money` gains `subtract` and `covers` (a currency-guarded "is at least"). The
ledger entry is a `TransactionType.DEBIT` carrying `balance_after`, exactly like a credit.

Application: `DebitWallet` mirrors `CreditWallet` — one `UnitOfWork.atomic()`, **idempotent by
`source_reference`** (a repeated debit for the same payment never double-spends), the wallet
row **locked** (`select_for_update`, no lost updates), and a `wallet.debited` audit with the
before/after balance. A wallet that does not exist (or cannot cover the amount) is refused and
nothing is written — a debit never lazily creates an empty wallet.

### Pay-with-wallet is its own use case, bridging like `PaidOrders`/`WalletCredit`
Unlike a gateway method, wallet payment settles at initiation, so it is a dedicated
`PayWithWallet` use case (payment application) rather than a `PaymentGateway.start` (whose
contract deliberately does not move money). In one transaction it: resolves the order
owner-scoped and re-checks payability (still pending, no active payment); captures the amount
from the order total; creates the `wallet` payment; **debits the shopper's wallet** for the
full amount through a narrow, primitive-typed `WalletDebit` port; **captures** the payment;
marks the order **paid** via the existing `PaidOrders` bridge; and audits `payment.initiated`
+ `payment.captured`. Any failure — an uncovered balance above all — rolls the whole thing
back, leaving no payment, no debit, and an unpaid order. A guest is refused up front
(`WalletPaymentRequiresUserError`): a wallet always belongs to a registered user.

The `WalletDebitAdapter` delegates to `DebitWallet` (its nested `atomic()` is a savepoint under
the payment's transaction, so the two commit together) and **translates** the wallet's
`InsufficientWalletFundsError` into the payment context's own `InsufficientWalletBalanceError`
— so no wallet-domain exception crosses the seam, exactly as `WalletCreditAdapter` isolates the
refund path.

### Transport: one checkout endpoint, dispatched by method
`POST payments/` keeps its single shape. The view routes `method: "wallet"` to `PayWithWallet`
and every other method to the gateway-backed `InitiatePayment`; both return a `PaymentResult`
(for wallet, `next_action: none`, and the payment already `captured`). A guest wallet attempt
and an uncovered balance both map to **409**. The amount is never client-supplied — it is the
order total, resolved server-side.

### UI
At checkout the wallet is offered only to a **signed-in shopper whose wallet holds credit**,
and is **selectable only when the balance covers the order total** (an empty wallet is not
shown; a funded-but-short wallet is shown disabled with an explanation). This gating is a pure
affordance: the shown balance and total are the server's exact strings (never recomputed), and
the backend re-checks and refuses an uncovered payment, so the client can never overspend. On
success the order is already paid, so the shopper lands straight on the paid order; the wallet
page shows the `order_payment` debit and the reduced balance.

## Consequences
- The wallet is now a full credit/debit ledger: refunds fund it, checkout spends it — end to
  end, atomic, and idempotent.
- Full-stack Playwright E2E covers the loop (fund via refund → pay a new order with the wallet
  → order paid, payment captured, balance debited to zero) plus the boundary (the option is
  not offered once the balance is spent). `seed_e2e` still resets the wallet for determinism.
- Deferred (see ROADMAP): card-to-card, and the `OrderPlaced`/`PaymentCaptured` event-bus
  publication carried over from Phase 3. The two narrow wallet concurrency edges logged in
  `ISSUES.md` under ADR 0039 apply equally to a first-ever debit racing wallet creation; both
  remain integrity-preserving (atomic + row lock + unique constraints) and retryable.
