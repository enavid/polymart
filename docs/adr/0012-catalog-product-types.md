# ADR 0012 — Catalog: product types (attribute templates)

- Status: Accepted
- Date: 2026-06-28

## Context
ADR 0011 introduced the **Attribute** — a reusable, typed property definition.
On its own an attribute describes nothing; a niche is modelled by saying *which*
attributes a kind of product has. That is the **ProductType**: a named template
(coffee, lipstick, brake pad) that assigns an ordered set of attributes. It is
the second Phase 2 slice and the bridge between the attribute vocabulary and the
products that will follow.

## Decision
The slice extends the existing `catalog` bounded context (no new app):

- `domain/catalog/` — the `ProductType` entity and the `ProductTypeCode` value
  object. A product type *references* attributes by code (it does not own them),
  keeps them in a stable display order, and rejects a duplicate reference
  (`DuplicateAttributeAssignmentError`). Whether a referenced attribute actually
  exists is **not** a domain concern: the entity cannot reach persistence, so
  referential existence is validated one layer out.
- `application/catalog/` — the `ProductTypeRepository` port and the use cases
  (`CreateProductType`, `GetProductType`, `ListProductTypes`). `CreateProductType`
  is injected with both repositories: it builds the entity (fail-fast on malformed
  codes, blank name, or duplicate references), then verifies every referenced
  attribute exists via the `AttributeRepository` (`UnknownAttributeError`), then
  persists. Creation emits a structured log and a durable audit entry
  (`product_type.created`) naming the actor.
- `infrastructure/catalog/` — `ProductTypeModel` plus an explicit ordered
  through model, `ProductTypeAttributeModel` (carrying a `position`, unique per
  `(product_type, attribute)`). `DjangoProductTypeRepository.add` persists the
  type and all its attribute links in one `transaction.atomic()`; reads
  `prefetch_related("attribute_links__attribute")` so the mapper never triggers a
  per-row query.
- `interface/api/catalog/` — thin DRF views over `catalog/product-types/`, behind
  the same global `manage_catalog` permission as attributes. Domain exceptions map
  to 400 / 404 / 409.

### Why an explicit ordered through model
Attribute order is meaningful (it drives display and form layout), so the
assignment is not a plain `ManyToManyField` but an explicit through model with a
`position` column. The plain M2M descriptor was deliberately omitted from
`ProductTypeModel`: every read must respect order and go through
`attribute_links`, so an unordered `.attributes.all()` accessor would be a
foot-gun (and dead code). This mirrors Saleor's `AttributeProduct` ordering model.

### Why existence is validated in the use case, not the entity
The dependency rule keeps the domain free of persistence. The entity owns
*structural* invariants (valid codes, no duplicates); the use case owns
*referential* ones (the attribute must exist). The repository keeps a final
defensive guard — if a validated attribute has vanished by the time links are
written (a concurrent-deletion race), it raises `UnknownAttributeError` and the
atomic insert rolls back, leaving nothing half-built. The attribute FK is
`on_delete=PROTECT`, so an attribute in use cannot be deleted in the first place.

## Consequences
- The white-label model can now express a niche: typed attributes composed into
  named product types, fully tested at 100% coverage.
- Products and variants (the next slices) attach to a product type and will carry
  *values* for its attributes; the value's conformance to each attribute's
  type/choices will be enforced there.

### Known limitations / deferrals
- **No update/delete of product types yet**, and no reordering or
  add/remove of an assignment after creation. Editing assignments interacts with
  products already built on the type (which attribute values must be back-filled or
  dropped), so it waits for the product slice.
- **Product-level vs variant-level attributes** are not yet distinguished: every
  assignment is currently a product-level attribute. The variant slice will add the
  variant-attribute distinction (as in Saleor's product/variant attribute split).
