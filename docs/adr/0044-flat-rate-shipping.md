# ADR 0044 — Flat-rate shipping methods (Phase 5, first slice)

- Status: Accepted
- Date: 2026-07-11

## Context
Phase 5 (fulfilment & inventory) opens with shipping. Until now an order's `total` was exactly
the sum of its line totals — checkout captured goods prices and a shipping address, but no
delivery charge. Selling physical goods needs a shipping cost that the shopper chooses at
checkout and that becomes part of what they owe.

This first slice is deliberately the **smallest coherent shipping increment**: flat-rate
methods only. Shipping *zones* (province/city matching), weight/table rates, label
printing/tracking, and BOPIS are later Phase 5 slices; multi-source inventory and tax are
separate slices again. The goal here is to build the **port/adapter seam** every future rate
model plugs into, and to relax the order's money invariant to include a captured shipping cost —
without hard-coding any carrier (per the project rule that shipping providers are adapters).

## Decision

### A new `shipping` bounded context (flat-rate, config-backed)
A full Clean-Architecture context (`domain` / `application` / `infrastructure` / `interface`):

- **Domain** — a `ShippingMethod` entity (a stable `ShippingMethodCode`, a display `name`, a flat
  `Money` price, and an estimated `min_days`/`max_days` delivery window), plus the context's own
  `Money`/`ShippingMethodCode` value objects (a bounded context owns its own primitives; it never
  imports a neighbour's). Pure Python, self-validating, `Decimal`-only money.
- **Application** — a `ShippingMethodReader` port with `available_for(channel)` and
  `get(channel, code)`, and two thin use cases: `ListShippingMethods` (for the storefront
  chooser) and `GetShippingMethod` (resolve one, raising `ShippingMethodNotFoundError`).
- **Infrastructure** — `SettingsShippingMethodReader` resolves methods from the
  `SHIPPING_METHODS` Django setting keyed by channel slug (like `PAYMENT_CARD_TO_CARD`). Flat-rate
  is configuration in this slice; a later slice moves rates to an admin-managed model *behind the
  same port* without the domain noticing. A malformed config entry is skipped (logged), never
  fatal to the chooser.
- **Interface** — `GET /shipping/methods/?channel=<slug>` (public: methods are channel
  configuration, not shopper data), price projected as an exact string.

### The order captures the chosen method (invariant relaxed)
The order context gains its own narrow `ShippingRateReader` port (`quote(channel, method_code,
currency) -> ShippingQuote | None`) — the order context asks "what does this method cost here?"
and captures the answer; whether the rate is config or a table is invisible to it. A
`ConfiguredShippingRateReader` adapter bridges order→shipping (delegating to `GetShippingMethod`),
returning `None` for an unknown method or one priced in a currency that does not match the order —
so checkout refuses it rather than capturing an invented or mismatched rate. No shipping-domain
type crosses back: the result is the order context's own `ShippingQuote`.

`PlaceOrder` gains a `shipping_method` on its command and, before the transaction (a pure config
read, like the address), quotes it — an unknown method raises `UnknownShippingMethodError` (→ 400)
and never enters the unit of work. The quoted cost is captured as a new `CapturedShipping` value
object (`method_code`, `method_name`, `cost`) on the `Order` aggregate. The aggregate's money
invariant is relaxed from `total == Σ line_totals` to **`total == Σ line_totals + shipping.cost`**;
`Order` exposes `items_subtotal` and `shipping_cost` so the goods total and the delivery charge
stay individually addressable. Shipping is **optional** on the aggregate (`shipping = None`): a
manual/pre-invoice order (`CreateManualOrder`) still has no delivery charge, and orders that
predate this slice reload as `shipping = None` (their persisted `total` is unchanged).

Persistence adds `shipping_cost` / `shipping_method_code` / `shipping_method_name` columns
(migration backfills existing rows with `0` / `""`, which the mapper reads as "no captured
shipping"). Placement audits the `shipping_method` + `shipping_cost`, and the `OrderPlaced` event
carries the grand total (goods + shipping) exactly as before.

### Storefront
Checkout fetches the channel's methods and shows a chooser (name, flat price, estimated window)
in the review step; the first method is preselected so a priced total shows immediately. The
order summary shows a **subtotal / shipping / total** breakdown, and the order-detail page shows
the same. Every money value on screen is the server's — the one place the UI *combines* two server
amounts (the pre-placement preview total = subtotal + selected shipping) uses exact scaled-integer
arithmetic (`sumMoneyStrings`), never binary-float; the authoritative grand total is still the
placed order's. The shopper must pick a method to place the order (the backend also requires it).

## Consequences
- Orders now carry a real, captured shipping charge that is part of the total, audited, and shown
  broken out. The port/adapter seam means zones and weight/table rates are additive later slices
  that swap the adapter, never a domain rewrite.
- **Config**: `SHIPPING_METHODS` is empty by default; dev/test/E2E define a deterministic set for
  `ir-main` (`standard`, `express`, and a free `free` method). Payment/wallet tests select `free`
  so their amount assertions stay focused on payment mechanics, not shipping cost.
- **Testing**: unit tests cover the shipping domain/use cases and the relaxed order invariant +
  `PlaceOrder` quoting (against fakes); integration tests cover the settings reader, the
  `/shipping/methods/` endpoint, the order→shipping bridge (including the currency-mismatch and
  unknown-method refusals), and checkout persisting/reloading the captured shipping with the
  grand total; frontend component tests cover the chooser, the breakdown, and method-switching;
  the checkout/guest E2E asserts the captured breakdown (goods + standard shipping = grand total)
  end-to-end against the real stack.
- **Deferred (later Phase 5 slices)**: shipping zones + admin panel, weight/table rates, label
  printing/tracking, BOPIS; and staff choosing a shipping method on a manual order (manual orders
  currently carry no delivery charge).
