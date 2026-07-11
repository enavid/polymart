# ADR 0025 — Catalog: storefront read API + product publication

- Status: Accepted
- Date: 2026-06-29

## Context
Every catalog endpoint so far is a **management** surface behind the global
`manage_catalog` permission. The storefront needs the opposite: a **public,
read-only** way to browse products — list, filter, search, and read one — so a
niche's catalog can be seen in the storefront (the Phase 2 goal).

A public surface raises a visibility question the management API never had: the
project is secure-by-default (`IsAuthenticated`) and a product has no notion of
being "live". Exposing every product anonymously would leak drafts. So this slice
also introduces an explicit **publication** gate.

## Decision
- **Product publication flag.** `Product` gains `is_published: bool` (default
  `False` — nothing is exposed by accident). It is a structural product field, not
  a separate aggregate. A dedicated admin use case `SetProductPublished` flips it,
  behind `manage_catalog`, and records a `product.publish_changed` before/after
  audit entry naming the actor (publishing is the boundary between the private
  catalog and the public web, so it is audited like other sensitive changes).
- **A read-side port, separate from the write repository.** `ProductQueryRepository`
  (`search` / `get_published_by_code`) is distinct from `ProductRepository` because
  browsing is a different access pattern (filtered, paged, published-gated) than
  managing one aggregate — a light CQRS split. `search` returns a `ProductPage`
  (the windowed items **plus** the full match count) so the caller can paginate.
- **Use cases.**
  - `SearchCatalogProducts` — **forces `published_only=True`** onto the filters (the
    flag is never taken from the caller, so the public API can never be asked for
    drafts), validates the page window, and delegates the query. `ProductFilters`
    carries the optional `search` / `category` / `collection` / `product_type`
    criteria, all AND-combined.
  - `GetPublishedProduct` — reads one product, treating a draft as **404**.
- **Filtering & search (adapter).** `DjangoProductQueryRepository.search` builds the
  queryset: `is_published` when restricted, `product_type__code`, the
  `category_links` / `collection_links` membership joins, and an `icontains` match
  on name **or** code for `search`. The ORM parameterises every term, so a
  user-supplied search string cannot inject SQL. Results are ordered by code; the
  total is counted on the filtered set before windowing.
- **Pagination.** `limit` (default 20, hard ceiling 100) and `offset` (≥ 0),
  validated in the use case — an out-of-range page is a domain `InvalidPaginationError`
  → **400**. The hard ceiling means one request can never ask the database for an
  unbounded result set.
- **Endpoints.**
  - `GET /api/v1/catalog/storefront/products/` — public (`AllowAny`), paged list of
    **published** products with the filters above. Envelope: `{count, limit, offset,
    results}`.
  - `GET /api/v1/catalog/storefront/products/<code>/` — public detail of one
    published product (404 for a draft/unknown).
  - `PUT /api/v1/catalog/products/<code>/publication/` — admin publish/unpublish
    (`manage_catalog`), body `{is_published}`.

### Why a separate public projection (no `id`)
The storefront payload is projected by `_storefront_product_payload`, which omits
the internal database `id`: the public key is the `code`, and not exposing the
sequential id avoids handing anonymous callers an enumeration handle. The
management payload keeps `id` (and now also reports `is_published`).

### Why a draft is 404, not 403
`GetPublishedProduct` / `get_published_by_code` raise `ProductNotFoundError` for an
unpublished product, indistinguishable from a missing one. A 403 would confirm that
a product with that code exists — an existence leak. 404 reveals nothing.

## Update (2026-07-02) — primary image in the projection
The list and detail projections now include an `image` field: the product's
primary image, or `null` when it has none (the client then renders a monogram
placeholder). There is no product-level image in this model — media lives on
variants (ADR 0017) — so the read *promotes* one variant image to represent the
product: the first media asset (lowest position) of the product's first variant
(lowest SKU) that carries any media. This is resolved by a new
`ProductQueryRepository.primary_images(codes)` query (one batched query for a
page), surfaced through a `GetStorefrontProductImages` read use case, and is not
channel-scoped (an image is the same in every channel). A true product-level media
surface can supersede this later without changing the payload shape.

## Consequences
- The storefront can browse, filter, search, and read the catalog without
  authentication, while drafts stay invisible until an admin publishes them.
- The query side is isolated behind its own port, so a future move to a search
  engine (Typesense/Meilisearch, Phase 8) can replace the adapter without touching
  the use cases.

### Known limitations / deferrals
- **Substring search, not relevance.** `icontains` on name/code is the "basic
  search" the roadmap asks for; ranked / typo-tolerant / faceted search is Phase 8.
- **No per-channel visibility or pricing in the projection.** The list/detail return
  product fields only; per-channel price (ADR 0023), variants, and stock are fetched
  through their own endpoints. Embedding them into the PLP/PDP payload is a
  storefront-UI concern (a later slice).
- **No attribute-value facet filtering** (e.g. `roast=dark`) yet — only
  category/collection/type/text. Facets are a Phase 8 enrichment.
- **Offset pagination.** Simple and sufficient here; cursor pagination for large
  catalogs can come with the search-engine slice.
