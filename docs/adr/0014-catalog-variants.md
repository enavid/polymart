# ADR 0014 — Catalog: product variants identified by SKU

- Status: Accepted
- Date: 2026-06-28

## Context
ADR 0013 delivered the **product** head: a product built on a product type,
carrying conforming attribute values and JSONB metadata. A product is not the
thing a customer actually buys, though — they buy a *sellable unit* (a 250g bag, a
1kg bag) with its own stock-keeping identity. This slice adds that unit: the
**ProductVariant**, a child of a product distinguished by a globally unique
**SKU**. It is the entity inventory, pricing, and cart/checkout will later hang
off, so getting its identity right (unique, stable, race-safe) matters now.

## Decision
The slice extends the existing `catalog` bounded context (no new app):

- `domain/catalog/` — the `ProductVariant` entity and the `Sku` value object. The
  entity references its parent product by code and owns only its structural rule
  (a non-blank, bounded display name). `Sku` is canonicalized to **upper case** and
  validated against a strict slug shape, so one physical item can never be split
  across two casings (`abc-1` vs `ABC-1`).
- `application/catalog/` — the `VariantRepository` port and the use cases
  (`CreateVariant`, `GetVariant`, `ListProductVariants`). `CreateVariant` builds the
  entity (fail-fast on a malformed SKU or blank name), verifies the parent product
  exists, then persists. Creation emits a structured log and a durable audit entry
  (`variant.created`) naming the actor.
- `infrastructure/catalog/` — `ProductVariantModel` (FK to the product, `unique`
  SKU column) with its mapper and `DjangoVariantRepository`. `add` resolves the
  parent product (raising `ProductNotFoundError` if it vanished concurrently) and
  translates a unique-SKU `IntegrityError` into `VariantAlreadyExistsError`. Reads
  `select_related("product")` so the mapper never triggers a per-row query.
- `interface/api/catalog/` — thin DRF views. Variants are **nested** under their
  product for listing/creation (`catalog/products/<code>/variants/`) and addressed
  globally by SKU for retrieval (`catalog/variants/<sku>/`), behind the same global
  `manage_catalog` permission.

### Why the SKU is the variant's identity (and upper-cased)
A SKU is a stock-keeping unit: the stable key that inventory and fulfilment use to
name one physical item. It must therefore be unique across the whole catalogue
(enforced by a DB unique constraint, not merely per-product) and have a single
canonical form. Upper-casing is the convention for SKUs and removes an entire class
of "same item, two records" bugs. Uniqueness is defended twice: a use-case
pre-check for a clean `409`, and the database constraint as the source of truth for
the concurrent-insert race.

### Status-code mapping
- Creating a variant under a product that does not exist → **404** (the parent in
  the nested route is missing), not 400.
- A malformed SKU or blank name → **400**.
- A SKU already taken → **409**.
- Retrieving an unknown SKU, or listing variants of an unknown product → **404**.

SKU lookup is case-exact against the stored canonical (upper-case) form; clients
always receive the canonical SKU from create/list responses, mirroring how product
codes are looked up by their exact slug.

## Consequences
- A product can now expose multiple sellable units, each with a unique SKU — the
  foundation the pricing and inventory slices will build on, at 100% coverage.
- `on_delete=CASCADE` on the variant's product means variants never outlive their
  product; the product's own `PROTECT` on its type is unchanged.

### Known limitations / deferrals
- **No options/modifiers and no variant-level media yet** — the next Phase 2 slice.
  This slice models the variant head and its SKU only.
- **Variants carry no attribute values yet.** Distinguishing variants by *option*
  attributes (size, colour) depends on the still-deferred product-level vs
  variant-level attribute distinction (ADR 0012); until then variants are
  distinguished by SKU and name.
- **No price and no stock on the variant yet** — price is the per-channel pricing
  slice, stock is the inventory slice. Neither money (Decimal) nor quantity lives
  on the variant in this slice by design.
- **No update/delete of variants yet.**
