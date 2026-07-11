# ADR 0020 — Catalog: collections (manual grouping node)

- Status: Accepted
- Date: 2026-06-29

## Context
The roadmap pairs **categories** (a taxonomy tree, ADR 0018/0019) with
**collections** — curated merchandising groupings (`Featured`, `Summer Sale`).
Collections come in two flavours: *manual* (a hand-picked product list) and
*rule-based* (membership derived from a stored predicate). That is too much for one
reviewable slice, so it is split the same way categories were (node first, then
membership):

- **this slice (0020):** the collection **node** — create / read / list a manual
  collection, identified by a stable slug.
- **next slice:** manual **membership** — the curated, ordered product list.
- **after that:** **rule-based** collections — membership from a predicate.

This first slice deliberately ships no membership, exactly as ADR 0018 shipped the
category node before ADR 0019 added product↔category assignment.

## Decision
A collection mirrors the category node's shape but is **not** hierarchical: it is a
flat grouping, never a taxonomy node, so it has no `parent` and no cycle concern.

- `domain/catalog/` — a `Collection` entity (slug + name) and a `CollectionSlug`
  value object reusing the shared kebab-case slug rule. The entity owns only the
  structural rule (a non-blank, bounded name); a malformed slug is rejected by the
  value object. Errors mirror the category precedent: `InvalidCollectionSlugError`,
  `InvalidCollectionNameError`, `CollectionNotFoundError` (404 lookup),
  `CollectionAlreadyExistsError` (409 conflict).
- `application/catalog/` — a dedicated `CollectionRepository` port and the use cases
  `CreateCollection`, `GetCollection`, `ListCollections`. `CreateCollection`
  pre-checks the slug for a clean 409, persists, and records a
  `collection.created` audit entry plus a structured `collection_created` log
  naming the actor (the user's stable id, never PII).
- `infrastructure/catalog/` — `CollectionModel` (unique slug, no relations). The
  repository's `add` is a single-row INSERT with no `transaction.atomic()` wrapper
  (one INSERT is already atomic), translating a unique-constraint `IntegrityError`
  into `CollectionAlreadyExistsError` to close the check-then-act window. Migration
  `catalog/0010`.
- `interface/api/catalog/` — `GET/POST catalog/collections/` and
  `GET catalog/collections/<slug>/`, behind the same global `manage_catalog`
  permission (reads need auth, writes need the permission).

### Why a separate entity, not "a category without a parent"
A category is a *taxonomy node* (a product's place in a tree, browsed via
breadcrumbs); a collection is a *merchandising grouping* (a curated list surfaced as
a storefront block). They differ in membership semantics — a category will hold
products by classification, a collection by hand-picking and later by rule — and in
lifecycle, so they are separate aggregates with separate tables.

### Status-code mapping
- Creating a collection whose slug is taken → **409**.
- A malformed slug or blank name → **400**.
- Reading an unknown slug → **404**.

## Consequences
- Collections exist as first-class catalog configuration at 100% coverage, ready for
  the membership slice to hang a curated product list off.
- Collections are platform-global catalog configuration, so access is the global
  `manage_catalog` permission, not an object-scoped grant — no IDOR surface.

### Known limitations / deferrals
- **No membership yet** — a collection is just a named node until the next slice
  adds its curated, ordered product list.
- **No rule-based collections yet** — the slice after membership.
- **No publish/visibility flag** — a collection is always readable by an
  authenticated user for now; storefront visibility belongs to a later slice.
