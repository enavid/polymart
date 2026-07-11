# ADR 0026 — Catalog: product CSV import/export

- Status: Accepted
- Date: 2026-06-29

## Context
Phase 2's catalog item (roadmap line 162) closes with **import/export CSV**. A
white-label store is seeded and maintained in bulk: a niche arrives with a
spreadsheet of products, and an operator wants the catalog back out as a file. The
two slices before this one delivered simple inventory and the storefront read API;
this one delivers the bulk product round-trip.

"Import/export CSV" is broad, so the scope was fixed deliberately:

- **Scope: products only** — the standard product CSV. One row per product carrying
  its `code`, `name`, `product_type`, `is_published`, category membership, and its
  attribute values. Variants/prices/stock are intentionally **out** of this slice
  (a variant CSV is a multi-row parent/child shape with per-channel money and stock
  locks — its own future slice). This mirrors how Shopify/WooCommerce ship a
  product CSV and manage variants/collections separately.
- **Execution: synchronous + all-or-nothing.** The whole file is validated and then
  persisted in one transaction; any invalid row fails the whole import and *every*
  row error is reported, so the operator fixes the file once rather than row by row.
  An async (Celery) pipeline was rejected for now: the catalog has no Celery wiring
  yet and large-file scale belongs with the Phase 3 infrastructure.

## Decision
- **Format-agnostic application, format at the edge.** The use cases speak only in
  `ProductRow` objects (a flat DTO: code, name, product_type, is_published,
  categories, attribute values). Turning rows into CSV bytes and back is a transport
  detail owned by an interface-layer codec (`csv_io.py`), so the domain/application
  never imports `csv`. Columns: the fixed
  `code,name,product_type,is_published,categories` followed by one `attr:<code>`
  column per attribute seen; category slugs share a cell, joined by `|`.
- **Export — `ExportCatalogProducts`.** A read-only use case: it loads every product
  and each product's category membership and shapes them into rows. The endpoint
  (`GET /catalog/products/export/`) streams a `text/csv` attachment. Export is a
  **read**, so it follows the catalog's read posture (any authenticated user) — the
  same data is already reachable through the management product reads, so gating a
  bulk read more strictly than the per-row reads it duplicates would be theatre.
- **Import — `ImportCatalogProducts`.** Two phases, owned by the use case:
  1. **Validate every row (read-only):** build the value objects, reject a code that
     repeats within the file (`DuplicateImportRowError`) or already exists
     (create-only — updating an existing product is a separate concern, there being
     no `UpdateProduct` use case yet), resolve the product type, conform the
     attribute values via the existing `normalize_attribute_values` domain service,
     and confirm every referenced category exists. Errors are **collected**, not
     raised on the first.
  2. **If any row failed:** write nothing and return the `ProductImportResult`
     (`created=0`, the per-row errors). Otherwise hand the batch to the writer.
  The import endpoint (`POST /catalog/products/import/`, multipart, behind
  `manage_catalog`) always returns the import-result shape: **200** when every row
  was created, **400** (with per-row or whole-file errors) when none were.
- **The transaction boundary lives in infrastructure.** The application cannot open a
  transaction (the dependency rule), so a dedicated write port `CatalogImportWriter`
  (adapter `DjangoCatalogImportWriter`) persists the validated batch inside one
  `transaction.atomic()`, reusing the product and product-category repositories
  (their own atomic blocks nest as savepoints). A lost insert race after validation
  surfaces as `ProductAlreadyExistsError` and rolls the **whole** batch back — a
  partial import is impossible.
- **Bulk audit + observability.** A successful import records a single
  `catalog.products_imported` audit entry (the `created_count`; a bulk operation has
  no single resource id) and a `catalog_products_imported` structured log naming the
  actor. No product data or PII is logged.
- **Denial-of-service bounds.** Two layers: the upload's **byte size** is capped at
  the transport edge (before it is parsed into memory), and the **row count** is
  capped in the use case (`ImportTooLargeError`), so neither a huge file nor a huge
  row set can exhaust memory or the database.
- **`is_published` parsing is fail-closed.** Only a clearly truthy token
  (`true`/`1`/`yes`) publishes; anything else — including blank or garbage — stays a
  draft, so a malformed cell never exposes a product by accident.

## Consequences
- Operators get a product round-trip: export the catalog, edit, re-import. The
  export is faithful enough that re-importing it is recognised (every row reports
  "already exists", since import is create-only).
- The application stays pure and format-agnostic; swapping CSV for another format
  (XLSX, JSON Lines) is a new codec at the edge, no use-case change.
- All-or-nothing keeps the catalog consistent: a 1000-row file with one bad row
  leaves nothing half-written and tells the operator exactly which rows to fix.

## Known limitations / accepted risks
- **Create-only.** A row whose code already exists is reported as an error, never an
  update. Bulk *editing* via CSV waits for a dedicated `UpdateProduct` use case (it
  needs its own diffing and `product.updated` audit), out of scope here.
- **Metadata and variants are not in the CSV.** Product `metadata` (a free-form JSON
  map) and variants/prices/stock are managed through their own APIs; the product CSV
  stays a flat, standard shape.
- **CSV formula injection is not mitigated, by design.** Export writes free-form
  fields (e.g. a product name) verbatim, so a cell beginning with `=`/`+`/`-`/`@`
  could be interpreted as a formula if the file is opened in a spreadsheet. The
  standard mitigation (prefixing such cells) is deliberately **not** applied because
  it would break export→import round-trip fidelity, and the data path is admin-only
  (writing the catalog needs `manage_catalog`; reading needs authentication) — the
  author and the reader of any such cell are both privileged users, so the residual
  risk is low. Revisit if catalog data ever becomes writable by lower-trust roles.
- **Export issues one category query per product (N+1).** Acceptable for an
  infrequent admin batch operation; it can be folded into a single prefetch later if
  export volume warrants it.
