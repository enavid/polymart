# ADR 0052 — Per-product tax classes + exemption + PLP/PDP with-tax display (Phase 5, tax slice)

- Status: Accepted
- Date: 2026-07-13

## Context
Per-channel VAT (ADR 0046) taxed every order at one channel rate. Phase 5 asks for tax
**classes** (standard / reduced / exempt), tax **zones** (destination-varying rate), and a
storefront **with-tax price display**. Two scope decisions frame this slice:

1. **Classes + exemption + PLP/PDP display now; tax zones deferred** to a follow-up (it
   mirrors shipping zones and is a cleanly separable dimension — a class×zone matrix — that
   deserves its own slice).
2. **A product's tax class lives on the product** as a `tax_class` code (default
   `"standard"`), mirroring the `weight_grams` field pattern; a channel config maps the code
   to a rate. It applies to all the product's variants.

## Decision
- **`Product.tax_class`** — a lower-case kebab-case code (default `"standard"`), validated on
  the entity, persisted on `ProductModel` (`catalog/0018`), round-tripped by the mapper,
  settable via the create-product API + admin form, and shown on the management product view.
- **Class-aware rate resolution.** `TaxRateReader.rate_for(channel, tax_class)` and the
  `GetTaxRate` / `CalculateTax` use cases gained a `tax_class` arg. `SettingsTaxRateReader`
  reads `TAX_CLASSES[channel]` (a `{code: rate}` map); a mapped class uses its rate (0 is a
  valid taxed-at-zero rate), the `standard` class falls back to the legacy `TAX_RATES[channel]`
  rate, and any *other* unmapped class is **exempt** (`None`). A malformed rate degrades to
  untaxed (logged), never crashing checkout.
- **Per-line tax at checkout.** The order context gained a narrow `ProductTaxClassReader` port
  (bridged to the catalog); `PlaceOrder`/`CreateManualOrder` now tax **each line at its
  product's class** (an exempt line contributes nothing) and shipping at the `standard` class,
  summing the tax-context-computed amounts into the captured total. The captured `rate` is the
  headline (highest) rate applied — the label shown on the order — while the authoritative tax
  lives in the amount, so a mixed-class order's total is exact and never recomputed from a
  single rate. An all-exempt, unshipped order captures no tax (`tax=None`).
- **PLP/PDP with-tax display.** The storefront product read exposes each product's resolved
  `tax_rate` (its class rate in the channel, or `null` for an exempt product / untaxed
  channel): the list read's `PriceSummary` gained `tax_rate` (resolved in the catalog repo,
  like availability), and the PDP variants read exposes the product's `tax_rate` in its
  envelope (resolved via the tax use case). The storefront shows a "prices include X% VAT"
  note on the product card and near the PDP prices; an exempt product shows none. Money stays
  the server's string; the note renders only the rate.

## Consequences
- Products can be standard, reduced, or exempt, and the order total honours each line's class
  exactly — exemption changes what the customer actually pays, not just a label.
- All still behind the `TaxRateReader` port, so the deferred admin-managed rate model / tax
  zones plug into the same seam without the order or catalog layers noticing.
- **Documented bounds:** the checkout *preview* still estimates tax at the standard rate on
  the full taxable base (the cart read does not carry per-line classes), so a cart with exempt
  items may preview slightly high — the placed order's tax is authoritative and correct (an
  extension of the existing "placed order's tax is authoritative" contract). A mixed reduced+
  standard order captures the headline (highest) rate as its label; a per-rate breakdown is
  deferred.
- **Deferred:** tax zones (destination-varying rate); an admin-managed rate/class model; a
  per-rate tax breakdown on the order; and a tax-class-aware checkout preview.

## Alternatives considered
- *Tax class on the product type* (rather than the product): rejected per the scope decision —
  per-product is more flexible (two products of one type can differ), and it mirrors the
  weight field already added to the variant.
- *A single order-level rate applied to the whole base:* rejected — it cannot express an
  exempt product, which is the core of the ask. Per-line summing is the honest model.
- *Building tax zones in this slice:* deferred — the class×zone matrix is a separate
  architectural step best done as its own slice, exactly as the shipping DB-admin panel was.
