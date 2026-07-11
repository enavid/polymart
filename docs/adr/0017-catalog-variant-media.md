# ADR 0017 — Catalog: variant media

- Status: Accepted
- Date: 2026-06-29

## Context
The final piece of the "options + media + attribute distinction" Phase 2 slice is
**variant-level media**: a customer comparing the red and the blue shirt expects to
see each one. ADR 0014 explicitly deferred media. This slice attaches an ordered
list of images to a variant.

## Decision
A variant carries an ordered list of **media assets**, each a URL reference with
optional alt text. Media is a *reference*, not a stored file — upload and storage
(object store, image processing) are infrastructure concerns for a later slice and
deliberately out of the domain here.

- `domain/catalog/value_objects.py` — `MediaAsset(url, alt_text="")`, immutable and
  self-validating. The URL may be **absolute** (`https://…`, a CDN/object-store
  link) or **site-relative** (`/media/…`, served by the platform), so themes can
  point at either without code changes; it must be non-blank, bounded, contain no
  whitespace, and start with an allowed prefix. Alt text is optional but bounded.
  Malformed input raises `InvalidMediaAssetError`.
- `domain/catalog/entities.py` — `ProductVariant` gains `media`; the entity rejects
  the same URL listed twice (`DuplicateMediaAssetError`).
- `application/catalog/use_cases.py` — `CreateVariantCommand` gains `media`;
  `CreateVariant` builds the assets (fail-fast on a malformed or duplicate URL) and
  records `media_count` on the audit entry.
- `infrastructure/catalog/` — `ProductVariantMediaModel` (FK to the variant
  `CASCADE`, `url`, `alt_text`, `position`; unique `(variant, url)`). It is written
  inside the same `transaction.atomic()` as the variant and its option values, and
  `prefetch_related` on reads.
- `interface/api/catalog/` — the variant serializers and payload expose `media`;
  creation accepts it (default empty), behind the same `manage_catalog` permission.
  A malformed or duplicate URL surfaces as `400`.

### Why a URL reference and not an upload
Storing/serving binaries (object store, signed URLs, thumbnails) is a substantial
infrastructure concern with its own ADR to come. Modelling media as a validated URL
now unblocks the storefront and the rest of the catalogue without coupling the
domain to a storage backend — when uploads arrive, they produce URLs that fit this
exact shape.

## Consequences
- Variants can present their own imagery, completing the Phase 2 "options + media"
  slice. The whole variant aggregate (head + options + media) persists atomically.
- 100% coverage maintained; the dependency rule holds (`MediaAsset` is a pure value
  object; the URL/storage backend stays outside the domain).

### Known limitations / deferrals
- **No file upload/storage** — media is a URL reference only; uploads, image
  processing, and a storage adapter are a later slice.
- **No product-level (shared) media** yet — only variant-level. Product galleries
  can be added with the same pattern when needed.
- No update/delete/reorder of media yet (create-only); order is the submitted order.
