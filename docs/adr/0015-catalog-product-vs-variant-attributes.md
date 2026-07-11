# ADR 0015 — Catalog: product-level vs variant-level attributes

- Status: Accepted
- Date: 2026-06-29

## Context
ADR 0012 gave a product type a single, ordered set of attributes, and ADR 0013
made products carry conforming values for them. But a white-label catalogue needs
two *kinds* of attribute on a type:

- **product-level** — shared by every variant of a product (origin, brand);
- **variant-level** — the *options* that distinguish one variant from another
  (weight, grind, size, colour).

Without that split there is nowhere to declare which attributes a variant may set,
so "options/modifiers" (ADR 0016) and a meaningful variant matrix are impossible.
This slice adds the distinction; it is the foundation the next two slices build on.

## Decision
The product type now holds **two ordered attribute sets** (Saleor's model):
`attributes` (product-level) and `variant_attributes` (variant-level).

- `domain/catalog/entities.py` — `ProductType` gains `variant_attributes`.
  Uniqueness is enforced **across both levels**: an attribute may not repeat within
  a level *or* appear on both, because an attribute that was simultaneously product-
  and variant-level would make a variant's value ambiguous. The rule lives in one
  place (`_reject_duplicate_assignments`) and raises the existing
  `DuplicateAttributeAssignmentError`.
- `application/catalog/use_cases.py` — `CreateProductTypeCommand` gains
  `variant_attributes`; `CreateProductType` validates that **both** levels
  reference real attributes and records `variant_attribute_count` on the audit
  entry alongside `attribute_count`.
- `infrastructure/catalog/` — the existing through table
  (`ProductTypeAttributeModel`) gains a `kind` discriminator
  (`product`/`variant`); `position` now orders attributes *within* their level
  (`Meta.ordering = (kind, position)`). The unique constraint on
  `(product_type, attribute)` is unchanged and now *also* enforces the domain's
  "not on both levels" rule at the database. The mapper buckets the ordered links
  back into the two sets; the repository writes both levels in one bulk insert.
- `interface/api/catalog/` — the product-type serializers and payload expose
  `variant_attributes`; creation accepts it (default empty), behind the same
  `manage_catalog` permission.

### Why a `kind` column rather than a second table
Both levels are the same shape (an ordered attribute reference) and share the
same uniqueness rule across the pair. One table with a discriminator keeps that
single constraint trivial to express and avoids duplicating the through-model,
mapper, and link-writing logic. Ordering by `(kind, position)` lets one query
return both levels already grouped and in order.

## Consequences
- A product type can now say *which* attributes are options. Variants gain a place
  to put their values (ADR 0016) and the catalogue can model a real variant matrix.
- Existing rows default to `kind="product"`, so the migration is backward
  compatible; product-level behaviour is unchanged.
- 100% coverage maintained; the dependency rule holds (the `kind` discriminator is
  an infrastructure detail — the domain only knows two tuples).

### Known limitations / deferrals
- Variants do not yet *use* `variant_attributes` — supplying conforming values is
  ADR 0016, and variant media is ADR 0017.
- No update/delete of a type's attribute assignments yet (create-only).
