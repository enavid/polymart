# Polymart

White-label, multi-niche e-commerce platform. One headless **Django** (Clean
Architecture) backend + a re-skinnable **React/Next.js** storefront that can sell
anything (coffee, cosmetics, car parts) by swapping theme & config.

Built test-first (TDD), Dockerized, with RBAC, structured logging + tracing, and
GitHub Actions CI/CD.

## Stack

- **Backend:** Django + DRF, PostgreSQL 16, Celery + Redis, Clean Architecture.
- **Frontend:** Next.js + React + TypeScript.
- **Quality:** pytest / Vitest / Playwright, ruff, mypy, ESLint.
- **Ops:** Docker + docker-compose, GitHub Actions, OpenTelemetry, structlog.

## Repository layout

```
backend/    Django backend (src/{domain,application,infrastructure,interface})
frontend/   Next.js storefront
infra/      Deployment assets (nginx, ...)
docs/       Research, features report, roadmap, ADRs, observability
.github/    CI/CD workflows
Makefile    Single entry point for all common commands
```

## Quick start (development)

Two ways to run the stack. **Native** (default) runs the app on your machine and
only the database/Redis in Docker; **Docker** runs everything in containers.

### Native (default)

```bash
make setup        # backend virtualenv (uv if present) + backend/.env
make up           # infra (db+redis) in Docker, migrate, then run app natively
make logs         # tail the native process logs
make down         # stop the app processes and the infra containers
```

### Docker (full stack)

```bash
make env
make docker-build
make docker-up
make docker-migrate
```

- Backend health: <http://localhost:8000/api/v1/health/>
- Auth (phone + password, tokens in HttpOnly cookies):
  `POST /api/v1/auth/login/`, `/auth/refresh/`, `/auth/logout/`, `GET /auth/me/`
- Onboarding & recovery (mobile OTP): `POST /api/v1/auth/otp/request/`,
  `/auth/register/`, `/auth/password-reset/`
- Catalog attributes (dynamic, white-label schema): `GET/POST
  /api/v1/catalog/attributes/`, `GET /api/v1/catalog/attributes/<code>/`
- Catalog product types (templates with product-level **and** variant-level
  attribute sets): `GET/POST /api/v1/catalog/product-types/`,
  `GET /api/v1/catalog/product-types/<code>/`
- Catalog products (typed attribute values + JSONB metadata): `GET/POST
  /api/v1/catalog/products/`, `GET /api/v1/catalog/products/<code>/`
- Catalog variants (sellable units with a unique SKU, conforming option values,
  and media): `GET/POST /api/v1/catalog/products/<code>/variants/`,
  `GET /api/v1/catalog/variants/<sku>/`
- Per-channel base price (Decimal money, currency derived from the channel):
  `GET/PUT /api/v1/catalog/variants/<sku>/prices/`
- Per-variant on-hand stock (set absolute, or adjust by a signed delta atomically
  — never oversells below zero): `GET/PUT/PATCH /api/v1/catalog/variants/<sku>/stock/`
- Product publication (admin gate for storefront visibility): `PUT
  /api/v1/catalog/products/<code>/publication/`
- Product CSV import/export (bulk; export is a read, import is admin-only,
  all-or-nothing with per-row errors): `GET /api/v1/catalog/products/export/`,
  `POST /api/v1/catalog/products/import/`
- Public storefront catalog read API (only published products; filter by
  `search`/`category`/`collection`/`product_type`, paginated; pass `channel` to
  enrich each item with a "from" price + availability): `GET
  /api/v1/catalog/storefront/products/`, `GET
  /api/v1/catalog/storefront/products/<code>/`
- Public storefront taxonomy (powers the PLP filter choosers): `GET
  /api/v1/catalog/storefront/categories/`, `/storefront/collections/`,
  `/storefront/product-types/`
- Catalog categories (hierarchical taxonomy tree): `GET/POST
  /api/v1/catalog/categories/`, `GET /api/v1/catalog/categories/<slug>/`
- Product↔category membership (set/read a product's categories): `GET/PUT
  /api/v1/catalog/products/<code>/categories/`
- Catalog collections (curated merchandising groupings): `GET/POST
  /api/v1/catalog/collections/`, `GET /api/v1/catalog/collections/<slug>/`
- Collection membership (set/read a collection's curated, ordered product list):
  `GET/PUT /api/v1/catalog/collections/<slug>/products/`
- Rule-based collections (membership from an attribute-value predicate, resolved
  dynamically): `GET/PUT /api/v1/catalog/collections/<slug>/rule/`,
  `GET /api/v1/catalog/collections/<slug>/rule/members/`
- Public storefront variant read (a published product's purchasable variants, each
  priced for a channel; draft → 404, price is an exact string or `null`):
  `GET /api/v1/catalog/storefront/products/<code>/variants/?channel=<slug>`
- Persistent cart (per-channel; add/update/remove, priced dynamically at read time;
  always the authenticated user's own cart — no cart id in the URL, so no IDOR;
  money is an exact string, an unavailable line is excluded from the total):
  `GET /api/v1/cart/?channel=<slug>`, `POST /api/v1/cart/items/`,
  `PUT/DELETE /api/v1/cart/items/<sku>/`
- API docs (Swagger): <http://localhost:8000/api/docs/>
- Frontend: <http://localhost:3000>
  - Storefront foundation: Tailwind v4 three-layer design tokens, shadcn/ui
    primitives, next-intl (Persian/RTL, Vazirmatn, Jalali formatting), and a
    typed cookie-JWT API client.
  - Phase 1 UI: `/login`, `/register`, `/password-reset`, `/account`, and an
    admin area (`/admin/access`, `/admin/channels`, `/admin/audit`).
  - Phase 2 catalog UI: a public storefront (`/products` PLP with
    search/category/collection/type filters + pagination, `/products/<code>` PDP)
    and a catalog admin area (`/admin/catalog/*`) covering attributes, product
    types, products (+ publication, categories, variants with option-values &
    media), variants (+ per-channel prices, stock set/adjust), hierarchical
    categories, collections (+ manual membership & dynamic rules), and CSV
    import/export.
  - Phase 3 cart UI: the PDP now lists purchasable variants with a per-channel
    price and an add-to-cart control, and `/cart` shows the shopper's cart
    (update/remove lines, server-computed totals, unavailable lines flagged) for
    the active channel.

> Native infra uses host ports 5432/6379. If they are taken, free them or set
> `POSTGRES_PORT` / `REDIS_PORT` in `backend/.env`; the native DB/cache settings
> are derived from those parts. A `DATABASE_URL`, if set, overrides `POSTGRES_*`.

## Common commands

```bash
make help              # list all targets
make check             # local gate: backend lint + type + test + full-stack E2E
make test              # backend tests + coverage
make fe-test           # frontend unit tests
make ci                # full quality gate (mirrors GitHub Actions)
make e2e-full          # full-stack browser E2E: start backend, seed, run Playwright
make seed-e2e          # seed the deterministic E2E dataset (dev only, idempotent)
```

`make e2e-full` runs the Playwright suite against the **real** stack (Django +
Postgres + the Next.js storefront): it brings up infra, seeds a known dataset
(`seed_e2e`), starts the backend, and drives every UI route in a browser — the
public storefront (home/PLP/PDP/cart), the auth/account screens, and the
access + catalog admin area — as real shopper and staff sessions, including
rigorous scenarios (logged-out/IDOR access control, an unavailable-in-channel
variant, empty search, a discriminating collection filter, pagination bounds, and
a cart flow asserting accumulation and exact multi-line totals). `make check`
runs it after the backend gate, so it needs Docker and a **stopped** native stack
(run `make down` first if `make up` is running). It stays out of `make ci`, which
is kept fast and hermetic. See
[`docs/adr/0029-full-stack-e2e-harness.md`](docs/adr/0029-full-stack-e2e-harness.md).

## Documentation

Start at [`docs/index.md`](docs/index.md). The engineering conventions every
contributor must follow live in [`CLAUDE.md`](CLAUDE.md).

## Status

Phase 0 (foundation) complete: monorepo scaffold, Clean Architecture skeleton,
Docker, Makefile, CI/CD, observability, and a tested walking skeleton (`health`).
Phase 1 (identity & access) complete on the backend (Channel context, phone-first
cookie-JWT auth, OTP, two-layer RBAC, audit log, token revocation) and now on the
frontend: the storefront foundation plus the Phase 1 UI (auth, account, and the
access/channel/audit admin area). Phase 2 (catalog core) is complete on the
backend and now surfaced in the UI: a public storefront (PLP/PDP) plus a full
catalog admin area (attributes, product types, products, variants, prices, stock,
categories, collections, rules, CSV import/export).
Phase 3 (cart → checkout → order) has started: the first slice — the persistent,
per-channel cart with dynamic pricing (add/update/remove, IDOR-safe, money-exact)
and the storefront variant/price read it needs — is complete on the backend and in
the UI (PDP add-to-cart + `/cart`). Checkout and order creation are the next slices.
A full-stack Playwright E2E harness (`make e2e-full`) now drives every UI route
against the real backend on a seeded dataset. Next: see
[`docs/03-roadmap.md`](docs/03-roadmap.md).
