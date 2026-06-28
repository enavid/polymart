# ADR 0004 — Channel as a first-class bounded context

- Status: Accepted
- Date: 2026-06-28

## Context
Polymart is a multi-niche, white-label platform: one installation must be able to
run several distinct storefronts, each with its own currency, locale, and (later)
pricing, tax, and inventory configuration. The roadmap (Phase 1) and `CLAUDE.md`
both require **Channel** to be a first-class domain entity from day one, because
almost every downstream concept (catalog prices, carts, orders, payments,
inventory) is scoped to a channel.

This is the first slice with real persistence — the `health` walking skeleton has
no database model — so it also establishes how an ORM-backed bounded context is
wired under Clean Architecture.

## Decision
The channel slice follows the four-layer layout from ADR 0002:

- `domain/channel/` — the `Channel` aggregate plus `Currency` and `ChannelSlug`
  value objects, all pure Python and self-validating. Invalid state is
  unrepresentable: a `Currency` cannot hold a non-ISO-4217 code, a `ChannelSlug`
  cannot hold a non-URL-safe value. Domain exceptions (`ChannelNotFoundError`,
  `ChannelAlreadyExistsError`, …) carry no framework coupling.
- `application/channel/` — the `ChannelRepository` port and the use cases
  (`CreateChannel`, `SetChannelStatus`, `GetChannel`, `ListChannels`). Use cases
  receive the repository by constructor injection and emit structured,
  audit-friendly log events on every mutation.
- `infrastructure/channel/` — a Django app (`label="channel"`) owning the
  `ChannelModel`, a mapper between ORM rows and domain entities, and
  `DjangoChannelRepository`, which translates ORM failures (`IntegrityError`,
  `DoesNotExist`) into domain exceptions so storage never leaks upward.
- `interface/api/channel/` — thin DRF views over `channels/`, secure-by-default
  (authentication required), translating domain exceptions to HTTP status codes
  (404 / 409 / 400) at the one boundary where the domain meets transport.

The ORM model lives under `infrastructure/`, registered in `INSTALLED_APPS` via
its `AppConfig` path (`src.infrastructure.channel.apps.ChannelConfig`). The
`slug` is the stable public business key used throughout the API; the database
`id` is the internal identity.

## Consequences
- Channel orchestration is unit-testable against an in-memory fake repository
  with no database; persistence and HTTP are covered by integration tests.
- The pattern (domain → port → use case → ORM repository → DRF view, wired by a
  per-slice composition root) is now proven for stateful contexts and is the
  template for catalog, cart, and orders.
- Currency is currently a validated ISO-4217 alpha code. A richer money model
  (minor units, formatting) belongs to the pricing context (Phase 2) and can wrap
  this value object without changing the channel domain.
- Fine-grained, channel-scoped RBAC (object permissions via django-guardian) is
  intentionally deferred to the identity/RBAC slice of Phase 1; for now the
  endpoints are protected by the project-wide `IsAuthenticated` default.
