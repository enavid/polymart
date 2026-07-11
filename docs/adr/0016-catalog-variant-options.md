# ADR 0016 — Catalog: variant option values (options/modifiers)

- Status: Accepted
- Date: 2026-06-29

## Context
ADR 0014 added the variant head (a sellable unit with a unique SKU) but, by its
own admission, variants carried no attribute values: there was no way to say *this*
variant is the 250g espresso grind. ADR 0015 then split a product type's attributes
into product-level and **variant-level** sets. This slice closes the loop: a
variant now supplies values for its product type's variant-level attributes — the
"options/modifiers" of the roadmap.

## Decision
A variant carries its own conforming option values, reusing the **same conformance
domain service** the product head uses (ADR 0013), pointed at the type's
*variant* attributes instead of its product attributes.

- `domain/catalog/entities.py` — `ProductVariant` gains `values`. The entity owns
  only the structural rule (at most one value per attribute,
  `DuplicateAttributeValueError`); type conformance is not its job.
- `application/catalog/use_cases.py` — `CreateVariantCommand` gains `values`.
  `CreateVariant` now loads the parent product, then its product type, then the
  definitions of that type's `variant_attributes`, and delegates to
  `normalize_attribute_values(definitions, variant.values)` — so option values are
  validated and canonicalized exactly like product values (numbers as `Decimal`,
  booleans as literals, dropdowns against declared choices, required options
  present). A value for an attribute that is not a *variant* attribute of the type
  is rejected as `UnassignedAttributeError`. The audit entry records `value_count`.
- `infrastructure/catalog/` — `ProductVariantAttributeValueModel` (FK to the
  variant `CASCADE`, FK to the attribute `PROTECT`, unique `(variant, attribute)`).
  The variant repository's `add` is now wrapped in `transaction.atomic()` so the
  variant row and its values commit together or not at all; reads
  `prefetch_related` the values so the mapper triggers no per-row query.
- `interface/api/catalog/` — the variant serializers and payload expose `values`;
  creation accepts them (default empty), behind the same `manage_catalog`
  permission. Conformance failures surface as `400`.

### Why reuse the conformance service
Product values and variant option values obey identical rules (typed, ordered,
choice-constrained, required-aware). Duplicating that logic for variants would
invite drift in money-adjacent parsing (e.g. `Decimal` handling). One pure domain
service, fed a different attribute set, keeps a single source of truth (DRY) and
keeps the rule in the domain.

## Consequences
- Variants are now distinguishable by their options, not just SKU and name — the
  catalogue can express a real variant matrix (250g/1kg × whole-bean/espresso).
- Persistence is atomic: a failed value insert leaves no half-built variant.
- 100% coverage maintained; the dependency rule holds (conformance stays a pure
  domain service; the use case only orchestrates).

### Known limitations / deferrals
- No enforcement yet that a product's variants form a *complete or unique* option
  matrix (no "two variants with identical options" guard) — deferred until pricing
  and inventory give variants a reason to be uniquely addressable by option set.
- No update/delete of variant values yet (create-only).
- Variant media is the sibling slice, ADR 0017.
