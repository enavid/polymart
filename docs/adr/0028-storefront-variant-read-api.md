# ADR 0028 — Catalog: storefront variant/price read API

- Status: Accepted
- Date: 2026-07-01

## Context
Phase 2's public storefront read (ADR 0025) exposes published products at the
**product** level only — it does not return variants. That was noted as a
deliberate deferral: a shopper browsing the PDP could see a product but not the
purchasable units under it, so there was nothing to add to a cart.

The cart slice (ADR 0027) needs exactly that surface: to add a line, the PDP must
offer the product's variants with each one's price in the active channel. This
slice closes the Phase-2 deferral **additively** — a new public endpoint, with the
existing Phase-2 storefront endpoints left untouched — and was explicitly
authorised by the maintainer as in-scope for this unit.

## Decision
- `application/catalog/` — one read use case, `GetStorefrontProductVariants`, and a
  small result type `StorefrontVariant` (a variant plus its `ChannelPrice | None`).
  It resolves publication through the **existing** `ProductQueryRepository`
  (`get_published_by_code`), so a draft or unknown product is a 404 alike — the
  existence of an unpublished product is never leaked, exactly as the product-level
  read guarantees. It then lists the product's variants and, for each, picks the
  price matching the requested channel (or `None`). Read-only: no persistence, no
  audit. It reuses the existing `VariantRepository` and `VariantPriceRepository`
  ports rather than adding new ones.
- `interface/api/catalog/` — a new public (`AllowAny`) endpoint:
  - `GET /api/v1/catalog/storefront/products/<code>/variants/?channel=<slug>`
  - The response omits the internal `id` (the public key is the SKU, matching the
    product-level read) and renders the price `amount` as an **exact string** so the
    `Decimal` survives JSON; `price` is `null` when the variant has no base price in
    the channel (shown, but not purchasable there). A missing `channel` query param
    is a 400; a draft/unknown product is a 404.
  - The URL is registered **before** the product-detail pattern so the more specific
    `.../variants/` route is matched first.

## Consequences
- The PDP can now offer purchasable, per-channel-priced variants, and the cart's
  add-to-cart flow has a public source — the storefront is testable end-to-end.
- Additive and low-risk: the Phase-2 storefront list/detail endpoints and their
  tests are unchanged; only new code paths were added, all at 100% coverage.
- Still product-scoped browsing plus variant read — richer merchandising (variant
  media galleries, option pickers driven by variant attributes) can build on this
  endpoint without reshaping it.
- Known cosmetic pre-existing item: `drf-spectacular` reports an operationId
  collision between the storefront product **list** and **detail** GETs (both from
  Phase 2, unrelated to this endpoint); recorded in `ISSUES.md`, auto-resolved by
  the schema generator with a numeral suffix.
