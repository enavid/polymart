"""Unit tests for the Channel aggregate root."""
from __future__ import annotations

import pytest

from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import InvalidChannelNameError
from src.domain.channel.value_objects import ChannelSlug, Currency


def _channel(**overrides: object) -> Channel:
    defaults: dict[str, object] = {
        "slug": ChannelSlug("coffee"),
        "name": "Coffee Store",
        "currency": Currency("IRR"),
    }
    defaults.update(overrides)
    return Channel(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_builds_with_sensible_defaults(self) -> None:
        channel = _channel()

        assert channel.id is None
        assert channel.is_active is True
        assert channel.slug == ChannelSlug("coffee")
        assert channel.currency == Currency("IRR")

    def test_trims_the_display_name(self) -> None:
        assert _channel(name="  Coffee Store  ").name == "Coffee Store"

    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_rejects_a_blank_name(self, blank: str) -> None:
        with pytest.raises(InvalidChannelNameError):
            _channel(name=blank)

    def test_rejects_an_over_long_name(self) -> None:
        with pytest.raises(InvalidChannelNameError):
            _channel(name="x" * 256)


class TestStatusTransitions:
    def test_deactivate_flips_an_active_channel(self) -> None:
        channel = _channel(is_active=True)

        channel.deactivate()

        assert channel.is_active is False

    def test_activate_flips_an_inactive_channel(self) -> None:
        channel = _channel(is_active=False)

        channel.activate()

        assert channel.is_active is True

    def test_status_transitions_are_idempotent(self) -> None:
        channel = _channel(is_active=True)

        channel.activate()
        channel.activate()

        assert channel.is_active is True

    def test_set_active_reports_whether_state_changed(self) -> None:
        channel = _channel(is_active=True)

        assert channel.set_active(active=True) is False  # no-op
        assert channel.set_active(active=False) is True  # changed
        assert channel.is_active is False
