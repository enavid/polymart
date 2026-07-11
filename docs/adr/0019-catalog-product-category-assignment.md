# ADR 0019 — Catalog: product↔category assignment

- Status: Accepted
- Date: 2026-06-29

## Context
ADR 0018 added the category **tree**. A tree is only useful once products hang off
it, so this slice adds the **membership**: which categories a product belongs to.
It is the link that storefront browsing, breadcrumb navigation, and (later)
rule-based collections read from.

It is deliberately scoped to the *assignment* (set / read a product's categories).
Manual and rule-based **collections** remain a separate Phase 2 slice.

## Decision
Membership is modelled as its **own sub-resource**, not folded into the product
aggregate, so the existing product create/read path (and its repository contract)
is untouched:

- `domain/catalog/` — no new entity. A small domain service,
  `reject_duplicate_categories`, enforces the one rule that spans the whole
  assignment: a product references a category at most once (a repeated slug is a
  malformed request, surfaced as `DuplicateCategoryAssignmentError`, not silently
  collapsed). Two new errors mirror the attribute precedent: `UnknownCategoryError`
  (a referenced category does not exist → 400, distinct from the 404
  `CategoryNotFoundError` used for a lookup).
- `application/catalog/` — a dedicated port `ProductCategoryRepository` (replace /
  list) and the use cases `SetProductCategories` and `GetProductCategories`.
  `SetProductCategories` builds the slugs (fail-fast on a malformed/duplicate
  slug), confirms the product exists (its id anchors the audit entry) and every
  referenced category exists, then delegates the atomic replace. A separate port
  (rather than new methods on `ProductRepository`) keeps the interfaces segregated
  and leaves existing fakes untouched.
- `infrastructure/catalog/` — `ProductCategoryModel`, an ordered M2M through table
  (`unique(product, category)`, product FK `CASCADE`, category FK `PROTECT`).
  `DjangoProductCategoryRepository.replace` clears and reinserts the membership
  **inside one `transaction.atomic()`**, having taken a `select_for_update()` lock
  on the product row so two concurrent replaces of the same product serialize
  instead of interleaving into a unique-constraint error. Migration `catalog/0009`.
- `interface/api/catalog/` — a thin `GET`/`PUT` on
  `catalog/products/<code>/categories/`, behind the same global `manage_catalog`
  permission (reads need auth, writes need the permission).

### Why a replace (PUT), not add/remove
Setting the whole membership in one idempotent `PUT` is the simplest correct
contract: the request body *is* the desired final set, so re-sending it is a no-op
and there is no partial-update ambiguity. Add/remove deltas can be layered on later
if a UI needs them; they are not required to express membership.

### Status-code mapping
- Setting categories on a product that does not exist → **404** (the product in the
  URL is missing).
- A malformed or duplicated category slug, or a referenced category that does not
  exist → **400** (the offending value is in the request body).
- A successful set or read → **200** (a replace, not a creation).

### Audit & observability
- A successful set emits `product.categories_changed` with the before/after
  membership recorded as a deterministic, comma-joined slug string (the audit value
  type is a flat scalar, never a list), plus a structured `product_categories_set`
  log naming the actor (the user's stable id, never PII).

## Consequences
- Products can now be placed in the category tree, at 100% coverage — the data
  storefront PLPs and rule-based collections will read.
- Membership is platform-global catalog configuration, so access is the global
  `manage_catalog` permission, not an object-scoped grant — no IDOR surface.

### Known limitations / deferrals
- **No collections yet** (manual or rule-based) — the next Phase 2 slice.
- **No add/remove delta endpoints** — only whole-set replace, by design.
- **Membership is not shown on the product read payload** — it is read via the
  dedicated sub-resource; the product head can incorporate it later if a consumer
  needs both in one call.
- **No category-side listing** (`products in a category`) yet — that belongs to the
  catalog list/filter/search slice.
