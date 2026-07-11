# ADR 0018 — Catalog: hierarchical categories

- Status: Accepted
- Date: 2026-06-29

## Context
ADRs 0011–0017 delivered the catalog's *shape*: attributes, product types,
products, and the sellable variant (with option values and media). What was still
missing is the **taxonomy** — the tree that organises products for browsing and
that later collections, navigation, and storefront PLPs hang off. This slice adds
the first piece: a hierarchical **Category**, a self-referential tree of nodes
keyed by a stable slug.

It is deliberately scoped to the *category node itself* (create / get / list). The
roadmap line also names manual and rule-based **collections** and the
**product↔category** assignment; those are separate slices that build on this one.

## Decision
The slice extends the existing `catalog` bounded context (no new app):

- `domain/catalog/` — the `Category` entity and the `CategorySlug` value object.
  The entity references its parent **by slug** (`None` for a root) and owns only
  *structural* rules: a non-blank, bounded display name, and the rule that a
  category is never its own parent. `CategorySlug` reuses the catalog's strict
  kebab-case slug shape, matching the other catalog codes.
- `application/catalog/` — the `CategoryRepository` port and the use cases
  (`CreateCategory`, `GetCategory`, `ListCategories`). `CreateCategory` builds the
  entity (fail-fast on a malformed slug, blank name, or self-parenting), confirms a
  referenced parent exists, rejects a duplicate slug, then persists. Creation emits
  a structured log and a durable audit entry (`category.created`) naming the actor.
- `infrastructure/catalog/` — `CategoryModel` (a self-referential `parent` FK,
  `unique` slug column) with its mapper and `DjangoCategoryRepository`. `add`
  resolves the parent (raising `ParentCategoryNotFoundError` if it vanished
  concurrently) and translates a unique-slug `IntegrityError` into
  `CategoryAlreadyExistsError`. Reads `select_related("parent")` so the mapper
  never triggers a per-row query.
- `interface/api/catalog/` — thin DRF views on `catalog/categories/` (list/create)
  and `catalog/categories/<slug>/` (retrieve), behind the same global
  `manage_catalog` permission as the rest of the catalog (reads need auth, writes
  need the permission).

### Why cycles need no tree-walk in this slice
A cycle in the tree would require a category to be its own ancestor. On **creation**
the new slug is brand new, so it cannot yet be an ancestor of anything; the only
reachable cycle is the degenerate self-parent (`parent == slug`), which the entity
rejects structurally. A full ancestor-walk is only needed once **re-parenting**
exists — deferred with the update slice.

### Status-code mapping
- A malformed slug, a blank name, self-parenting, or a reference to a parent that
  does not exist → **400** (all surfaced as `CatalogError` from the create path;
  the parent is part of the request body, like a product's `product_type`).
- A slug already taken → **409**.
- Retrieving an unknown slug → **404**.

### Integrity
- The parent FK is `on_delete=PROTECT`: a category with children cannot be deleted
  out from under its subtree, so the tree is never silently orphaned. (No delete
  endpoint exists yet; this guards the database regardless.)
- Uniqueness is defended twice — a use-case pre-check for a clean `409`, and the
  database unique constraint as the source of truth for the concurrent-insert race.
- A category is a single row (no child tables), so its insert needs no
  `transaction.atomic()` wrapper — the one `INSERT` is already atomic. (Contrast
  the product/variant repositories, which wrap parent + child-table writes.)

## Consequences
- The catalog now has a taxonomy tree that collections, navigation, and storefront
  browsing will build on, at 100% coverage.
- Categories are platform-global configuration (not user-owned), so access is the
  global `manage_catalog` permission, not an object-scoped grant — no IDOR surface.

### Known limitations / deferrals
- **No product↔category assignment yet** — attaching products to categories is the
  next sub-slice; this slice models the tree only.
- **No collections yet** (manual or rule-based) — a separate Phase 2 slice.
- **No update / re-parent / delete of categories yet.** Re-parenting will need the
  ancestor-walk cycle check noted above.
- **No depth limit, ordering, or per-category metadata/media** — added when the
  storefront navigation slice needs them.
