# ADR 0022 — Catalog: rule-based collections (membership from a predicate)

- Status: Accepted
- Date: 2026-06-29

## Context
ADR 0020 shipped the collection **node** and ADR 0021 added its **manual
membership** (a curated, ordered product list), deferring rule-based collections
to "the next slice". This is that slice: a collection whose membership is derived
from a **predicate** over product attribute values rather than hand-picked — the
catalog analogue of Shopify "automated collections" / Saleor predicate-based
collections.

Products already store each attribute value in a **canonical, normalized string
form** (the conformance domain service from ADR 0013 normalizes number → `Decimal`
string, boolean → literal, dropdown → choice slug, text → trimmed at creation), so
a predicate can match on that stored form with exact string equality for every
input type. That observation shapes the operator set below.

## Decision
- `domain/catalog/` — no new entity (mirroring the membership slice, which added a
  service rather than an entity). New pieces:
  - `RuleOperator` enum: **`EQUALS` / `NOT_EQUALS`** only. Ordered/range operators
    (greater-than, …) need type-awareness (compare as `Decimal`, not string) and are
    a deliberate follow-up; equality on the canonical stored value is exact and
    well-defined for every input type today.
  - `RuleCondition` value object: `(attribute, operator, value)`, immutable,
    self-validating (non-blank, bounded comparison value).
  - Two pure domain services: `reject_duplicate_conditions` ("a rule lists each
    `(attribute, operator, value)` at most once"; the *same* attribute with a
    different operator or value is a distinct, allowed predicate, e.g.
    `roast != light AND roast != medium`), and `match_products` — which products a
    **conjunction** of conditions selects, evaluated against their attribute values.
  - Matching semantics, fixed and tested: a product matches iff **every** condition
    holds (AND). `EQUALS` requires the attribute to be present and equal;
    `NOT_EQUALS` holds when the product has no such value **or** a differing one (a
    missing attribute is "not equal to" any value). An **empty rule selects
    nothing** — a zero-condition conjunction would be vacuously true, but treating an
    unconfigured rule as "every product" is a footgun, so it is deliberately empty.
- `application/catalog/` — a dedicated `CollectionRuleRepository` port (replace /
  list, a facet separate from the curated membership) and three use cases:
  `SetCollectionRule` (build value objects → reject duplicates → confirm the
  collection exists → confirm every referenced **attribute** exists → atomic replace
  → `collection.rule_changed` audit with before/after as a deterministic
  `attribute:operator:value,…` string), `GetCollectionRule`, and
  `GetCollectionRuleMembers` (read-only: evaluate the rule against every product via
  `match_products` and return the matching codes; no persistence, no audit). An empty
  rule clears it. An unknown referenced attribute is a **400** (`UnknownAttributeError`),
  distinct from the **404** lookup of the collection's own URL.
- `infrastructure/catalog/` — an ordered through table
  `CollectionRuleConditionModel` (unique `(collection, attribute, operator, value)`,
  `position` for order). The collection FK is `CASCADE` (deleting a collection clears
  its rule) and the attribute FK is `PROTECT` (an attribute still referenced by a
  rule cannot be deleted), matching the container/member `on_delete` choices of the
  membership through row. `replace` runs in one `transaction.atomic()` and locks the
  collection row with `select_for_update()` so concurrent replaces serialize instead
  of interleaving into a unique-constraint error; a referenced attribute that
  vanished mid-replace surfaces as `UnknownAttributeError` and rolls the whole
  replace back. Migration `catalog/0012`.
- `interface/api/catalog/` — behind the same global `manage_catalog` permission:
  - `GET/PUT catalog/collections/<slug>/rule/` — read / fully replace the rule
    (`PUT` is idempotent; the empty list clears it).
  - `GET catalog/collections/<slug>/rule/members/` — resolve the products the rule
    currently selects.

### Status-code mapping
- Reading/replacing the rule (or resolving members) of an unknown collection → **404**.
- A malformed condition value, an unknown operator, a duplicate condition, or a
  referenced attribute that does not exist → **400**.

## Consequences
- A collection can now be **manual** (ADR 0021) or **rule-based** (here) — two
  independent facets. Computing a single *effective* membership (how a storefront
  combines a curated list with rule matches) is deliberately **out of scope** and
  belongs to the storefront PLP slice that consumes both.
- Rule membership is computed **dynamically on read** — always consistent with the
  current catalog, with no materialization to keep in sync and no background jobs
  (Celery is a Phase 3+ concern).

### Known limitations / deferrals
- **Equality operators only.** Range/numeric/`contains` operators are a follow-up;
  they need attribute-type-aware comparison (`Decimal`, ordering) rather than string
  equality.
- **Linear evaluation.** `GetCollectionRuleMembers` loads all products and matches in
  Python (O(products × conditions)). Fine at catalog scale for this phase; the upgrade
  path is to push the predicate into the query layer or a search index (Phase 8
  smart search), at which point materialization may also be reconsidered.
- **No combination semantics** between manual membership and the rule yet (see above).
