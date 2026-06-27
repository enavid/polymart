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

```bash
cp .env.example .env
make build
make up
make migrate
```

- Backend health: <http://localhost:8000/api/v1/health/>
- API docs (Swagger): <http://localhost:8000/api/docs/>
- Frontend: <http://localhost:3000>

## Common commands

```bash
make help              # list all targets
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
Next: see [`docs/03-roadmap.md`](docs/03-roadmap.md).
