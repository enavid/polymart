# ADR 0023 — Catalog: per-channel base price for variants

- Status: Accepted
- Date: 2026-06-29

## Context
The catalog can now describe *what* is sold (products, variants, attributes,
categories, collections) but not *for how much*. This slice adds the **base price**
— the list price of a sellable unit — which is the last catalog-core building block
before cart/checkout (Phase 3) can compute a total.

Price is **per channel** (ADR 0004 made the channel a first-class selling context
with its own currency). A variant — the sellable unit with a SKU (ADR 0014) — is
priced once per channel, and the currency is the channel's. This is the Saleor
`ProductVariantChannelListing` model.

Money is handled with the care the project reserves for financial code: a base
price is a fixed-point `Decimal`, never a binary `float`, and every change is
captured in a money-sensitive audit trail.

## Decision
- `domain/catalog/` — two new value objects and one service, no new entity
  (mirroring the membership/rule facets):
  - `Money` value object: `(amount: Decimal, currency: str)`, immutable and
    self-validating. The amount **must be a `Decimal`** (a `float`/`int` is
    rejected outright — the whole point of Decimal money), **finite**, **strictly
    positive** (a zero/free price is a promotion concern of a later phase, not a
    base price), and bounded to the stored precision (≤ 18 total digits, ≤ 4
    decimal places). `currency` is a three-letter ISO 4217 alpha code; full
    membership is the channel context's concern, so `Money` enforces only the
    structural shape.
  - `ChannelPrice` value object: `(channel: str, money: Money)` — a variant's price
    in one channel. The channel is referenced by slug (it lives in another bounded
    context); existence and currency are resolved in the application layer.
  - `reject_duplicate_channel_prices` domain service: a variant has at most one
    base price per channel; a repeated channel is a malformed request, not a
    silent last-wins overwrite.
- `application/catalog/` — a dedicated `VariantPriceRepository` port (replace /
  list, a facet separate from the variant's own attributes/media), a narrow
  `ChannelReader` port (`currency_of(slug) -> str | None`) that lets the catalog
  learn a channel's currency **without depending on the channel domain**, and two
  use cases:
  - `SetVariantPrices` — confirm the variant exists (404), then for each price
    **derive the currency from the channel** (an unknown channel is a 400) and
    build a `Money` (a malformed/zero/negative amount is a 400), reject duplicate
    channels, delegate the atomic replace, and record a `variant.price_changed`
    audit entry with before/after as a deterministic `channel=amount currency,…`
    string. An empty set clears all prices.
  - `GetVariantPrices` — read-only listing (404 if the variant is unknown).
  - **Currency is never client-supplied.** Deriving it from the channel removes a
    whole class of error (a price recorded in the wrong currency is impossible by
    construction) and keeps the channel the single source of truth.
- `infrastructure/catalog/` — `VariantPriceModel`: variant FK `CASCADE`
  (related name `prices`), `channel_slug`, a `currency_code` **snapshot** taken
  from the channel at write time (so a stored price stays self-describing), and an
  `amount` `DecimalField(18, 4)`. Unique `(variant, channel_slug)`. `replace` runs
  in one `transaction.atomic()` and locks the variant row with `select_for_update()`
  so concurrent replaces serialize instead of racing into a unique-constraint
  error. `DjangoChannelReader` reads the channel's `currency_code`. Migration
  `catalog/0013`.
- `interface/api/catalog/` — behind the global `manage_catalog` permission:
  - `GET/PUT catalog/variants/<sku>/prices/` — read / fully replace the price set
    (`PUT` is idempotent; the empty list clears it). The amount is serialized as a
    **string** so the exact `Decimal` survives JSON (a float would reintroduce the
    rounding error Decimal exists to avoid); the response carries the derived
    currency.

### Status-code mapping
- Reading/replacing the prices of an unknown variant → **404**.
- A malformed/zero/negative amount, an over-precise amount, an unknown channel, or
  a duplicate channel price → **400**.

### Why no cross-app foreign key to the channel
The price references the channel by **slug**, not a database foreign key. The
channel is a separate bounded context, and keeping the reference soft keeps the
catalog schema decoupled and its migrations independent. Existence is enforced at
the use-case layer (the `ChannelReader` port → 400). Channels are not deletable in
the current model, so there is no orphan-row race today; if channel deletion is
added later it must reconcile or block on referencing prices.

## Consequences
- A variant can be priced independently in every channel, each in that channel's
  own currency — the foundation cart/checkout pricing (Phase 3) will read.
- Prices are stored, not derived: there is no rule/computation layer yet
  (sale prices, cost-plus, tiered/volume pricing, tax-inclusive display) — those
  are later phases (promotions, tax).

### Known limitations / deferrals
- **Base price only.** No sale/discount price, cost, or minimum-order price; those
  belong to the promotions phase.
- **Structural precision, not currency-exact.** `Money` enforces a fixed maximum
  scale (4 dp) rather than each currency's own ISO exponent (IRR 0, USD 2, BHD 3).
  Currency-exact rounding is a follow-up; until then an over-precise amount for a
  zero-decimal currency is accepted and stored as given.
- **Currency snapshot.** The price stores the channel's currency at write time; the
  model has no use case to change a channel's currency, so drift cannot occur today.
- **No FK integrity** to the channel (see above).
