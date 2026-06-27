# ADR 0003 — Observability stack (structured logging + tracing)

- Status: Accepted
- Date: 2026-06-27

## Context
The project requires proper logging and distributed tracing from the start so
that every phase is debuggable in development and production.

## Decision
- **Logging:** structlog over the stdlib logging pipeline. JSON output in
  production, console output in development. A `RequestIDMiddleware` binds a
  per-request correlation id (`request_id`) to the log context and echoes it on
  the response.
- **Tracing:** OpenTelemetry, vendor-neutral, exported via OTLP. Auto-
  instrumentation for Django, psycopg, Redis, and Celery. Disabled by default and
  enabled with `OTEL_ENABLED=true`; all imports are guarded so the app runs
  without the optional `observability` extra.
- **Correlation:** a structlog processor injects the active `trace_id`/`span_id`
  into every log line, linking logs to traces.
- **Metrics:** deferred to a later phase using the same OpenTelemetry SDK.

See `docs/04-observability.md` for usage details.

## Consequences
- One consistent, queryable log format across services.
- Logs and traces are correlated out of the box.
- Tracing adds zero overhead when disabled and no hard dependency when the extra
  is not installed.
