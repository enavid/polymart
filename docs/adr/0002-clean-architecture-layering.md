# ADR 0002 — Clean Architecture layering for the Django backend

- Status: Accepted
- Date: 2026-06-27

## Context
The platform must be highly testable (TDD), maintainable over many phases, and
able to swap infrastructure (payment gateways, search, cache) without rewriting
business logic. Uncle Bob's Clean Architecture is a stated project requirement.

## Decision
The backend is organised into four layers under `backend/src/`, with the
dependency rule pointing strictly inward:

- `domain/` — pure Python entities, value objects, and business rules. No
  framework imports (no Django, DRF, ORM, Celery).
- `application/` — use cases (interactors) and ports (abstract interfaces).
  Depends only on `domain`.
- `infrastructure/` — adapters implementing the ports (Django ORM repositories,
  payment/shipping/tax gateways, cache, event bus).
- `interface/` — thin transport (DRF serializers/views/urls). Parses input,
  invokes a use case via a composition root, serializes output.

Each vertical slice gets a small composition root (e.g.
`interface/api/<slice>/container.py`) that wires concrete adapters into the use
case. The walking skeleton is the `health` slice.

## Consequences
- Business logic is unit-testable against fake adapters with no database.
- Django is a replaceable detail; the ORM lives only in `infrastructure`.
- Some boilerplate is accepted. Pragmatism: full ceremony applies to the core
  domain (catalog, cart, orders, pricing, payments, inventory); trivial CRUD with
  no business rules may use Django more directly.
