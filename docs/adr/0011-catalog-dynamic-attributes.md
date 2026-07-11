# ADR 0011 — Catalog: dynamic attributes (EAV-like foundation)

- Status: Accepted
- Date: 2026-06-28

## Context
Polymart is a multi-niche, white-label platform: the same backend must describe a
coffee, a cosmetic, and a car part without code changes. That requires a flexible,
data-driven product schema rather than fixed columns per niche. The roadmap
(Phase 2 — Catalog Core) opens with **product types + dynamic attributes**, the
EAV-like core every later catalog concept (product types, products, variants,
pricing) builds on.

This ADR covers the first Phase 2 slice: the **Attribute** — a reusable, typed
property definition (roast level, origin, weight, …). Product types, which compose
attributes, and products, which hold attribute values, are deliberately deferred
to the following slices so each stays small and reviewable.

## Decision
The catalog slice follows the four-layer layout used since ADR 0004:

- `domain/catalog/` — the `Attribute` entity plus the `AttributeCode` and
  `AttributeChoice` value objects (pure Python, self-validating) and the
  `AttributeInputType` enum. Invalid state is unrepresentable: a code must be a
  URL-safe slug, a choice value must be a slug with a non-blank label, and the
  entity enforces the input-type/choice coherence rule — a choice type
  (`dropdown`) must carry at least one choice; every other type must carry none.
  Choice values must be unique within an attribute. Domain exceptions
  (`AttributeNotFoundError`, `AttributeAlreadyExistsError`,
  `AttributeChoicesRequiredError`, …) carry no framework coupling.
- `application/catalog/` — the `AttributeRepository` port and the use cases
  (`CreateAttribute`, `GetAttribute`, `ListAttributes`). Use cases receive the
  repository by constructor injection and, on creation, emit a structured log and
  a durable audit entry (`attribute.created`) naming the actor.
- `infrastructure/catalog/` — a Django app (`label="catalog"`) owning
  `AttributeModel` and a child `AttributeChoiceModel`, a mapper, and
  `DjangoAttributeRepository`, which persists the attribute and all its choices in
  one `transaction.atomic()` and translates ORM failures (`IntegrityError`,
  `DoesNotExist`) into domain exceptions so storage never leaks upward.
- `interface/api/catalog/` — thin DRF views over `catalog/attributes/`,
  secure-by-default: reads require authentication, writes require the global
  `manage_catalog` permission. Views translate domain exceptions to HTTP status
  codes (400 / 404 / 409) at the one boundary where the domain meets transport.

### Why `is_choice_type`, not a hard-coded set
The choice rule asks one question — "does this input type draw its value from a
declared set?" — answered by a single `AttributeInputType.is_choice_type` flag.
The entity never enumerates the membership inline, so adding `multiselect` (a
future choice type) or `rich_text` (a future free type) is a one-line enum change,
not an edit scattered across the validation logic.

### Why choices live in a child table
An attribute's choices are stored as one row each (`AttributeChoiceModel`) rather
than an opaque JSON blob, so a choice value stays an individually constrained,
queryable key. A per-attribute unique constraint
(`uniq_choice_value_per_attribute`) makes a product's reference to a choice
unambiguous. This mirrors the established catalog modelling in Saleor/Vendure.

### RBAC
`manage_catalog` is owned by the catalog context (declared in
`domain/catalog/permissions.py`, mirrored on `AttributeModel.Meta.permissions`)
and bundled into a new `catalog_admin` role by the registry. The catalog schema is
platform-global configuration, so management is a **global** permission, never
object-scoped — unlike per-channel management. Reads are open to any authenticated
user.

## Consequences
- The flexible product schema has its foundation: typed, reusable attribute
  definitions with coherent choice rules, fully tested at 100% coverage.
- A second bounded context now contributes permissions to the registry, exercising
  the multi-context registry/sync path beyond channel + identity.
- The white-label model is half-expressed: an attribute exists but nothing composes
  it yet. The next slice introduces **product types**, which assign a set of
  attributes to a named template; products and attribute *values* follow.

### Known limitations / deferrals
- **No update/delete of attributes yet.** Only create/read are exposed. Editing a
  definition (especially changing input type or removing a choice already used by a
  product) needs the product slice to reason about referential impact; deferred.
- **Choice ordering** is captured by a `position` column but not yet reorderable
  through the API; it follows insertion order on create.
- **Attribute values** (a product's actual data for an attribute) are out of scope
  here — they arrive with the product slice, where the value's conformance to the
  attribute's type/choices will be enforced.
