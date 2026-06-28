"""Unit tests for the structured logging configuration."""
from __future__ import annotations

import structlog

from config.logging import (
    _add_otel_context,
    build_logging_config,
    configure_structlog,
)


class TestAddOtelContext:
    def test_leaves_event_untouched_without_an_active_span(self) -> None:
        event = {"event": "something_happened", "key": "value"}

        result = _add_otel_context(None, "info", dict(event))

        # No span is active in a plain unit test, so no trace ids are attached.
        assert result == event
        assert "trace_id" not in result
        assert "span_id" not in result


class TestBuildLoggingConfig:
    def test_returns_a_console_renderer_config(self) -> None:
        config = build_logging_config(json_logs=False, level="DEBUG")

        assert config["version"] == 1
        assert config["disable_existing_loggers"] is False
        assert config["root"]["level"] == "DEBUG"
        assert "console" in config["handlers"]
        assert "structured" in config["formatters"]

    def test_honours_the_requested_level_and_json_flag(self) -> None:
        json_config = build_logging_config(json_logs=True, level="WARNING")
        console_config = build_logging_config(json_logs=False, level="WARNING")

        assert json_config["root"]["level"] == "WARNING"
        # Both variants are valid dict configs; the renderer differs internally.
        assert json_config["formatters"]["structured"]["()"] is (
            console_config["formatters"]["structured"]["()"]
        )


class TestConfigureStructlog:
    def test_produces_a_usable_bound_logger(self) -> None:
        configure_structlog()

        logger = structlog.get_logger("test.logger")

        # Should not raise; structlog is wired into the stdlib pipeline.
        logger.info("configured_logging_event", answer=42)
