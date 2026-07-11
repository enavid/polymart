# ADR 0046 — Per-channel value-added tax (Phase 5, tax slice)

- Status: Accepted
- Date: 2026-07-11

## Context
Phase 5 (fulfilment & inventory) has, so far, taught the order total to include a captured
shipping cost (ADR 0044 flat-rate, ADR 0045 zones). The next money component an Iranian store
owes is **value-added tax (VAT / مالیات بر ارزش افزوده)** — a percentage the shopper pays on top
of goods and delivery. Until now an order's `total` was exactly `Σ lines + shipping`; the
pre-invoice even carried a `tax: null` placeholder awaiting this slice.

This slice adds tax on the **same port/adapter seam** the shipping slices established: build the
context and the seam, relax the order's money invariant to include a captured tax, and show the
tax broken out at checkout and on the order — without hard-coding a rate in the domain. Following
the shipping progression (flat-rate first, zones second), this slice is deliberately the
**smallest coherent tax increment**: a single per-channel rate. Per-product **tax classes**,
destination **tax zones**, tax-exempt handling, and PLP/PDP tax-inclusive price display are
explicitly deferred to later slices that plug into this same seam.

## Decision

### A new `tax` bounded context (config-backed, single rate per channel)
A full Clean-Architecture context (`domain` / `application` / `infrastructure` / `interface`):

- **Domain** — a `TaxRate` value object (a `Decimal` percentage in `[0, 100]`, `fraction` giving
  the multiplier form) and the context's own `Money`; a `calculate_tax(taxable, rate)` domain
  service. This service is the **first place in the codebase where money is multiplied by a
  fraction rather than an integer**, so it is the first place rounding is unavoidable: it
  quantizes the result to the stored money precision (4 dp) with an explicit **`ROUND_HALF_UP`**
  rule, `Decimal` throughout (never binary `float`), so the computed tax is deterministic and
  always representable as a captured amount.
- **Application** — a `TaxRateReader` port with `rate_for(channel) -> TaxRate | None`, and two thin
  use cases: `GetTaxRate` (for the storefront) and `CalculateTax` (channel + taxable → applied
  rate + rounded amount, or `None` when the channel is untaxed).
- **Infrastructure** — `SettingsTaxRateReader` resolves the rate from the `TAX_RATES` Django
  setting keyed by channel slug (like `SHIPPING_METHODS` / `PAYMENT_CARD_TO_CARD`). A malformed
  value degrades to "untaxed" (logged), never fatal to checkout. A later slice moves rates to an
  admin-managed model *behind the same port* without the domain noticing.
- **Interface** — `GET /tax/rate/?channel=<slug>` (public: the rate is channel configuration, not
  shopper data), rate projected as an exact string or `null`.

### The order captures the tax (invariant relaxed)
The order context gains its own narrow `TaxCalculator` port (`calculate(channel, taxable) ->
TaxQuote | None`) — it asks "what tax is due on this taxable amount here?" and captures the
answer. A `ConfiguredTaxCalculator` adapter bridges order→tax (delegating to `CalculateTax`); no
tax-domain type crosses back, and the amount is the tax context's computed value, **never
recomputed** by the order context, so the captured amount and the total can never drift.

`PlaceOrder` and `CreateManualOrder` compute the **taxable base = goods subtotal + shipping cost**
(a manual order has no shipping, so its base is the subtotal alone), resolve the tax inside the
unit of work (a pure settings read + arithmetic, no locking), and capture a new `CapturedTax`
value object (`rate`, `amount`) on the `Order`. The aggregate's money invariant is relaxed from
`total == Σ lines + shipping.cost` to **`total == Σ lines + shipping.cost + tax.amount`**; `Order`
exposes `tax_amount` alongside `items_subtotal`/`shipping_cost`. Tax is **optional** on the
aggregate (`tax = None`): a channel that levies no tax, and orders that predate this slice, reload
as `tax = None` (their persisted `total` is unchanged). A configured rate of `0` is distinct from
`None` — it captures a zero-amount tax line.

Persistence adds `tax_amount` (default `0`) and `tax_rate` (nullable — `NULL` is the "no captured
tax" sentinel) columns (migration `order/0006`, backfilling existing rows to `0` / `NULL`).
Placement audits the tax amount, and the `OrderPlaced` event carries the grand total (goods +
shipping + tax) exactly as before. The pre-invoice's `tax` placeholder becomes the real captured
amount; its `grand_total` equals the order total (which already includes the tax).

### Storefront
Checkout fetches the channel's rate and shows a **tax line** in the review breakdown (subtotal /
shipping / tax / total). The previewed tax is computed client-side with the **same exact
integer-scaled `ROUND_HALF_UP` arithmetic** as the backend (`taxAmountString`, unit-tested against
the domain service's values), so a preview never drifts from the amount the server captures; the
authoritative tax is still the placed order's. The order-detail and pre-invoice pages show the
same breakdown from the server's captured values. The rate itself is a display **label**
(`formatPercent`, Persian digits, trailing zeros dropped — «۹٪»), not money.

## Consequences
- Orders now carry a real, captured tax that is part of the total, audited, shown broken out, and
  round-trips through persistence. The port/adapter seam means tax classes and tax zones are
  additive later slices that swap/extend the adapter, never a domain rewrite.
- **Config**: `TAX_RATES` is empty by default (no channel taxed). dev/E2E set `ir-main` to `9`
  (Iran's VAT rate) so the breakdown and the E2E harness show a known tax on every placed order.
  The pytest suite deliberately leaves `TAX_RATES` empty so existing order/payment total
  assertions stay untaxed; tax-specific backend tests set it via `override_settings`.
- **Testing**: unit tests cover the tax domain/use cases and the relaxed order invariant +
  `PlaceOrder`/`CreateManualOrder` capturing tax (against fakes, with exact rounding); integration
  tests cover the settings reader, the `/tax/rate/` endpoint, the order→tax bridge (including the
  half-up rounding), and checkout persisting/reloading the captured tax with the grand total;
  frontend tests cover `taxAmountString`/`formatPercent`, the checkout tax line, the order/pre-
  invoice tax line; and the checkout/guest/zones/wallet/manual E2E specs assert the tax-inclusive
  breakdown end-to-end against the real stack.
- **Deferred (later Phase 5 slices)**: per-product tax classes, destination tax zones, tax-exempt
  products/customers, prices-with/without-tax display on the PLP/PDP, an admin-managed rate model,
  and choosing whether shipping is taxable per channel (this slice taxes goods + shipping).
