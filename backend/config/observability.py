"""OpenTelemetry tracing setup.

Tracing is optional and disabled by default. Enable it by setting
``OTEL_ENABLED=true`` and (optionally) ``OTEL_EXPORTER_OTLP_ENDPOINT``. Every
import below is guarded so the application runs unchanged when the
``observability`` extra is not installed.
"""

from __future__ import annotations

import os

_CONFIGURED = False


def _is_enabled() -> bool:
    return os.environ.get("OTEL_ENABLED", "false").lower() in ("1", "true", "yes")


def configure_tracing() -> None:
    """Initialise the global tracer provider and auto-instrumentation once."""
    global _CONFIGURED
    if _CONFIGURED or not _is_enabled():
        return
    _CONFIGURED = _setup_tracer_provider()  # pragma: no cover - needs otel + enabled


def _setup_tracer_provider() -> bool:  # pragma: no cover - exercised only with otel installed
    """Wire the OTLP exporter and auto-instrumentation. Returns success."""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return False

    resource = Resource.create(
        {"service.name": os.environ.get("OTEL_SERVICE_NAME", "polymart-backend")}
    )
    provider = TracerProvider(resource=resource)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _instrument()
    return True


def _instrument() -> None:  # pragma: no cover - exercised only when otel installed
    """Apply auto-instrumentation for the frameworks we use."""
    instrumentors = (
        ("opentelemetry.instrumentation.django", "DjangoInstrumentor"),
        ("opentelemetry.instrumentation.psycopg", "PsycopgInstrumentor"),
        ("opentelemetry.instrumentation.redis", "RedisInstrumentor"),
        ("opentelemetry.instrumentation.celery", "CeleryInstrumentor"),
    )
    for module_path, class_name in instrumentors:
        try:
            module = __import__(module_path, fromlist=[class_name])
            getattr(module, class_name)().instrument()
        except Exception:  # nosec B112 - instrumentation is best-effort and optional
            continue
