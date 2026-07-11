# ADR 0021 — Catalog: collection membership (manual, curated product list)

- Status: Accepted
- Date: 2026-06-29

## Context
ADR 0020 shipped the collection **node** (create / read / list) and deferred its
membership, exactly as ADR 0018 shipped the category node before ADR 0019 added
product↔category assignment. This slice adds the **manual membership**: the
curated, ordered list of products a collection groups. Rule-based collections
(membership derived from a stored predicate) remain a later slice.

The shape mirrors product↔category assignment (ADR 0019) with the container and
member roles swapped: there the product is the container and categories are the
members; here the **collection** is the container and **products** are the members.
One difference is intent — a category set is an unordered classification, whereas a
collection's membership is a *curated order* (the sequence a storefront block
renders), so the requested order is preserved as first-class data.

## Decision
- `domain/catalog/` — no new entity. A small domain service
  `reject_duplicate_products` enforces "a collection lists a product at most once"
  (a repeated code is a malformed membership, not a silently-collapsed set). Two
  errors mirror the category precedent: `DuplicateProductMembershipError` and
  `UnknownProductError` — a referenced product that does not exist → **400**,
  deliberately distinct from `ProductNotFoundError` (the 404 lookup of the
  collection's own URL).
- `application/catalog/` — a dedicated `CollectionProductRepository` port (replace /
  list) and the use cases `SetCollectionProducts` / `GetCollectionProducts`.
  `SetCollectionProducts` builds the value objects (fail fast on a malformed or
  duplicated code), confirms the collection exists (its id anchors the audit
  entry), confirms every referenced product exists, then delegates the atomic
  replace and records a `collection.products_changed` audit entry with before/after
  membership (a deterministic, comma-joined code string — an audit value is a flat
  scalar, never a list).
- `infrastructure/catalog/` — an ordered through table `CollectionProductModel`
  (unique `(collection, product)`, `position` for the curation order). The
  collection FK is `CASCADE` (deleting a collection clears its membership) and the
  product FK is `PROTECT` (a product still listed cannot be deleted), mirroring the
  category through row's container/member `on_delete` choices. `replace` runs in a
  single `transaction.atomic()` and locks the collection row with
  `select_for_update()` so two concurrent replaces of the same collection serialize
  instead of interleaving into a unique-constraint error. Migration `catalog/0011`.
- `interface/api/catalog/` — `GET/PUT catalog/collections/<slug>/products/` behind
  the same global `manage_catalog` permission. `PUT` is a full, idempotent
  replacement of the ordered list; the empty list clears membership.

### Status-code mapping
- Replacing/reading the membership of an unknown collection → **404**.
- A malformed code, a duplicated code, or a referenced product that does not
  exist → **400**.

## Consequences
- A collection now carries a curated, ordered product list, ready for the
  storefront and for the rule-based collections slice to build on.
- Replacement is atomic and serialized per collection, so a concurrent or partly
  failed replace never leaves a half-updated list.
- Membership is platform-global catalog configuration gated by `manage_catalog`,
  not an object-scoped grant — no IDOR surface.

### Known limitations / deferrals
- **Still no rule-based collections** — membership here is hand-picked; predicate
  membership is the next slice.
- **No per-product metadata on the membership** (e.g. a pin/feature flag) — only
  position is stored; richer curation data belongs to a later slice if needed.
