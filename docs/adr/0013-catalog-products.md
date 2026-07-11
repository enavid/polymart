# ADR 0013 — Catalog: products with conforming attribute values

- Status: Accepted
- Date: 2026-06-28

## Context
ADR 0011 defined typed **attributes**; ADR 0012 composed them into ordered
**product types**. ADR 0012 explicitly deferred one rule to "the product slice":
whether a product's *values* conform to its type's attributes. This is that
slice — the first catalog entity that carries real per-item data: a **Product**
built on a product type, supplying a value for some or all of the type's
attributes, plus free-form JSONB metadata.

## Decision
The slice extends the existing `catalog` bounded context (no new app):

- `domain/catalog/` — the `Product` entity, the `ProductCode` and `AttributeValue`
  value objects, and a **conformance domain service** (`services.py`). The entity
  owns only *structural* rules: a non-blank name, at most one value per attribute,
  and well-formed string-keyed metadata. Whether each value *conforms* to its
  attribute's input type — and whether required attributes are present — spans the
  product and the attribute definitions, so it lives in `normalize_attribute_values`,
  a pure function that takes the type's attribute definitions and the product's
  values and returns canonicalized values or raises a catalog error.
- `application/catalog/` — the `ProductRepository` port and the use cases
  (`CreateProduct`, `GetProduct`, `ListProducts`). `CreateProduct` builds the entity
  (fail-fast on malformed input), loads the product type and its attribute
  definitions (in declared order), delegates conformance to the domain service,
  then persists. Creation emits a structured log and a durable audit entry
  (`product.created`) naming the actor.
- `infrastructure/catalog/` — `ProductModel` (with a `metadata` `JSONField`, JSONB in
  Postgres) and `ProductAttributeValueModel`, an ordered child table (one row per
  value, unique per `(product, attribute)`). `DjangoProductRepository.add` persists
  the product and all its values in one `transaction.atomic()`; reads
  `select_related("product_type")` and `prefetch_related("attribute_values__attribute")`
  so the mapper never triggers a per-row query.
- `interface/api/catalog/` — thin DRF views over `catalog/products/`, behind the same
  global `manage_catalog` permission. Domain exceptions map to 400 / 404 / 409.

### Why conformance is a domain service, not entity or use-case logic
The rule needs two aggregates at once (the product's values and the attribute
definitions), so it belongs to neither entity. Putting it in the use case would
bury a core business rule in orchestration and risk it drifting framework-ward.
A pure domain service keeps the rule in the domain, unit-testable without Django,
while the use case stays responsible only for fetching the inputs and persisting
the result.

### Value typing and canonicalization
Values are stored as canonical strings (EAV-style), but each is validated against
its attribute's input type before storage:

- **number** parses with `Decimal` (never float); non-finite values (`NaN`,
  `Infinity`) and non-numeric text are rejected, and the canonical `Decimal`
  string is stored (preserving precision a float would drop). Negative numbers are
  allowed — a generic numeric attribute is not money; money is modelled separately
  with its own non-negative rule in the pricing slice.
- **boolean** accepts only `true`/`false` (case-insensitive), stored lower-case.
- **dropdown** must match one of the attribute's declared choice slugs.
- **plain_text** is trimmed and must be non-blank.

### Metadata
`metadata` is free-form, string-keyed, string-valued extension data, mirroring
Saleor's metadata. It is deliberately **not** a place for money or structured
domain data — keys and value lengths are bounded, and the field never holds
Decimal/price information.

## Consequences
- A full niche catalog can now be expressed end to end: typed attributes →
  product types → products carrying validated values, at 100% coverage.
- Referential integrity is enforced by `on_delete=PROTECT` on the product's type
  and on each value's attribute, so a type or attribute in use cannot be deleted.

### Known limitations / deferrals
- **No variants, options/modifiers, SKU, or media yet** — those are the next
  Phase 2 slice. This slice models the product head and its product-level
  attribute values only.
- **No update/delete of products yet**, and values cannot be edited after
  creation; editing interacts with variants and pricing, so it waits for those
  slices.
- **Product-level vs variant-level attributes** are still not distinguished (every
  value is product-level), as noted in ADR 0012.
