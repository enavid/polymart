# ADR 0029 — Full-stack end-to-end test harness

- Status: Accepted
- Date: 2026-07-01

## Context
The UI had grown to cover the whole product surface — a public storefront
(home, PLP, PDP, cart), the auth/account screens, and the access + catalog admin
areas — but the only browser coverage was two Playwright specs (`health`,
`login`), both of which **mock the backend at the network layer**. Nothing
exercised the real front-to-back path: a mocked login never proves the cookie
session works, a mocked product list never proves the storefront read actually
returns the seeded catalog.

The goal of this slice: a browser suite that drives the **real** Next.js
storefront against the **real** Django backend, covering every route the UI
exposes, so a regression anywhere in the stack (serializer, permission, price
computation, query wiring) is caught end to end.

Two shaping decisions were taken with the maintainer:
1. **Full-stack, not mocked** — the suite runs against a live backend + database.
2. **Cover everything** — all ~22 routes, including the admin area.

## Decision

### Deterministic seed (`seed_e2e`)
A full-stack suite needs a known fixture. A single idempotent Django management
command, `seed_e2e`, writes it: a **shopper** user, a **staff** user holding the
catalog/access/channel admin roles, a channel, and a small **published** catalog
(a product type, three products with variants + per-channel prices + stock — one
deliberately out of stock — a category tree, and a collection with members). It
also clears the shopper's cart, so every run starts from a known state.

- It lives in a dedicated `devtools` app and **guards on `DEBUG`**: it raises
  rather than run against a non-DEBUG (production-like) database. The app is
  installed everywhere but the command is inert outside DEBUG.
- Users are created through the manager's `create_user`, which normalises the
  phone to canonical E.164 — the exact form login looks up. (A raw insert would
  store an un-normalised phone that login, and the command's own idempotency
  check, could never match. This bit us during bring-up and is now a regression
  test.)
- It is covered by integration tests (idempotency, the DEBUG guard, the seeded
  shape, cart clearing) so it counts toward the backend coverage gate like any
  other code.

### Playwright projects + real sessions
- A **setup** project logs the seeded users in **through the real UI** and saves
  their HttpOnly cookie sessions to disk (`storageState`); it also warms the
  dev-server routes (Next JIT-compiles per route on first hit — warming once,
  process-globally, keeps the first spec to touch a route from flaking).
- **public** (unauthenticated), **shopper** (reuses the shopper session), and
  **staff** (reuses the staff session) projects each depend on setup. Specs are
  split into `public/`, `shopper/`, `staff/` folders matched per project.
- The seeded fixture is mirrored in `tests/e2e/fixtures/seed.ts`; the TS mirror
  and the Python command are a documented pair that must stay in sync.
- Money is asserted by reproducing the UI's `Intl.NumberFormat` in the test and
  matching the **displayed** value, keeping the "server is the source of truth,
  the UI does not recompute" contract honest at the browser boundary.

### Orchestration
`make e2e-full` brings up infra, migrates, then `scripts/e2e.sh` starts the
backend, seeds, and runs Playwright (which starts the frontend itself); the
backend is always torn down on exit. `make seed-e2e` runs the seed alone. `make
e2e` still runs Playwright against an already-running, already-seeded stack. The
local gate `make check` runs `e2e-full` after the backend lint/type/test, so a
green `make check` now means the full stack works front-to-back (it therefore
needs Docker and a stopped native stack — `assert-stopped` guards against a
running `make up`).

### Rigorous scenarios (not just happy paths)
Beyond each route rendering, the suite asserts the hard cases: logged-out access
control / IDOR (a signed-out visitor is refused the cart/account surfaces and
sees no protected admin data), a variant priced only in another channel showing
"unavailable" with no add control, an empty search result, a collection filter
that discriminates members from non-members, a pagination boundary, and a cart
flow that checks repeat-add accumulation and exact multi-line totals (money by
reproduced `Intl` formatting, never a client recomputation). The seed carries the
fixtures these need (e.g. an unavailable variant priced in a secondary channel).

## Consequences
- Every UI route is now exercised against the real backend: the storefront read,
  the cookie-JWT session, the dynamic cart pricing (add → priced line + total →
  update → remove), the OTP request path, and every admin manager/detail page
  rendering its seeded data. 29 checks, green via one command.
- The suite needs a live stack. It **is** wired into the local `make check`
  (so the everyday gate proves the whole stack), but stays **out** of `make ci`,
  which is kept fast and hermetic, matching how CI already treats `make e2e`.
- The full OTP-verify path is not driven in the browser: in DEBUG the code is
  only logged and stored one-way-hashed, so a browser test cannot read it. That
  path stays covered by the backend integration tests; the E2E covers the real
  request path the UI drives.
- One retry is allowed even locally, as a safety net for dev-server cold compiles
  on top of the explicit warmup; a genuine failure still fails both attempts.
