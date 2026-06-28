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
- API docs (Swagger): <http://localhost:8000/api/docs/>
- Frontend: <http://localhost:3000>

> Native infra uses host ports 5432/6379. If they are taken, free them or set
> `POSTGRES_PORT` / `REDIS_PORT` in `backend/.env`; the native DB/cache settings
> are derived from those parts. A `DATABASE_URL`, if set, overrides `POSTGRES_*`.

## Common commands

```bash
make help              # list all targets
make check             # quick local gate: backend lint + type + test
make test              # backend tests + coverage
make fe-test           # frontend unit tests
make ci                # full quality gate (mirrors GitHub Actions)
```

## Documentation

Start at [`docs/index.md`](docs/index.md). The engineering conventions every
contributor must follow live in [`CLAUDE.md`](CLAUDE.md).

## Status

Phase 0 (foundation) complete: monorepo scaffold, Clean Architecture skeleton,
Docker, Makefile, CI/CD, observability, and a tested walking skeleton (`health`).
Phase 1 (identity & access) in progress: the **Channel** bounded context and a
phone-first **custom user model with cookie-based JWT auth** are delivered.
Next: see [`docs/03-roadmap.md`](docs/03-roadmap.md).
