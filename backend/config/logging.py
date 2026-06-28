"""Structured logging configuration (structlog + stdlib).

Logs are emitted as JSON in production and as human-readable colored output in
development. Every log line carries contextual fields bound via
``structlog.contextvars`` (e.g. ``request_id``) and, when a trace is active, the
OpenTelemetry ``trace_id`` / ``span_id`` for log-to-trace correlation.
"""
from __future__ import annotations

from typing import Any

import structlog


def _add_otel_context(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Attach the active OpenTelemetry trace/span ids to the log event.

    Returns the event unchanged when tracing is not installed or no span is
    active, so logs work identically with or without the observability extra.
    """
    ids = _active_trace_ids()
    if ids is not None:  # pragma: no cover - only when an otel span is active
        event_dict["trace_id"], event_dict["span_id"] = ids
    return event_dict


def _active_trace_ids() -> tuple[str, str] | None:
    """Return ``(trace_id, span_id)`` for the active span, or None."""
    try:
        from opentelemetry import trace
    except Exception:  # pragma: no cover - otel is an optional extra
        return None

    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx is None or not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")  # pragma: no cover


SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    _add_otel_context,
]


def configure_structlog() -> None:
    """Wire structlog so its loggers feed into the stdlib logging pipeline."""
    structlog.configure(
        processors=[
            *SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def build_logging_config(json_logs: bool, level: str) -> dict[str, Any]:
    """Return a Django ``LOGGING`` dict rendering through structlog."""
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    renderer,
                ],
                "foreign_pre_chain": SHARED_PROCESSORS,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "structured",
            },
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "django": {"handlers": ["console"], "level": level, "propagate": False},
            "celery": {"handlers": ["console"], "level": level, "propagate": False},
        },
    }
