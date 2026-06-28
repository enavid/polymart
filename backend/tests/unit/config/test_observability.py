"""Unit tests for the OpenTelemetry tracing toggle."""

from __future__ import annotations

import pytest

import config.observability as observability


class TestIsEnabled:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes"])
    def test_truthy_values_enable_tracing(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_ENABLED", value)
        assert observability._is_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "off"])
    def test_other_values_disable_tracing(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OTEL_ENABLED", value)
        assert observability._is_enabled() is False

    def test_unset_disables_tracing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OTEL_ENABLED", raising=False)
        assert observability._is_enabled() is False


class TestConfigureTracing:
    def test_is_a_noop_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_ENABLED", "false")
        monkeypatch.setattr(observability, "_CONFIGURED", False)

        # Must not raise and must not flip the configured flag.
        observability.configure_tracing()

        assert observability._CONFIGURED is False

    def test_is_a_noop_when_already_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_ENABLED", "true")
        monkeypatch.setattr(observability, "_CONFIGURED", True)
        # Guard: if the early-return failed, this sentinel would be called.
        monkeypatch.setattr(
            observability,
            "_setup_tracer_provider",
            lambda: pytest.fail("should not set up a provider when already configured"),
        )

        observability.configure_tracing()
