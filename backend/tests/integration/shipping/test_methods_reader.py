"""Integration tests for the settings-backed shipping method reader."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

from src.infrastructure.shipping.methods import SettingsShippingMethodReader

pytestmark = [pytest.mark.integration]

_VALID = {
    "ir-main": [
        {
            "code": "standard",
            "name": "Standard post",
            "price": "50000",
            "currency": "IRR",
            "min_days": 3,
            "max_days": 5,
        },
        {
            "code": "express",
            "name": "Express courier",
            "price": "120000.5000",
            "currency": "IRR",
            "min_days": 1,
            "max_days": 2,
        },
    ],
}


class TestAvailableFor:
    @override_settings(SHIPPING_METHODS=_VALID)
    def test_reads_all_configured_methods_for_a_channel(self) -> None:
        methods = SettingsShippingMethodReader().available_for("ir-main")
        assert [m.code.value for m in methods] == ["standard", "express"]
        assert methods[0].price.amount == Decimal("50000")
        assert methods[1].price.amount == Decimal("120000.5000")

    @override_settings(SHIPPING_METHODS=_VALID)
    def test_an_unconfigured_channel_has_no_methods(self) -> None:
        assert SettingsShippingMethodReader().available_for("ghost") == ()

    @override_settings(SHIPPING_METHODS={})
    def test_no_configuration_at_all_has_no_methods(self) -> None:
        assert SettingsShippingMethodReader().available_for("ir-main") == ()

    @override_settings(
        SHIPPING_METHODS={
            "ir-main": [
                {
                    "code": "ok",
                    "name": "Fine",
                    "price": "1000",
                    "currency": "IRR",
                    "min_days": 1,
                    "max_days": 2,
                },
                {"code": "broken", "name": "No price"},  # malformed -> skipped
                {
                    "code": "bad-currency",
                    "name": "X",
                    "price": "1",
                    "currency": "RIAL",
                    "min_days": 1,
                    "max_days": 2,
                },  # invalid currency -> skipped
            ],
        }
    )
    def test_a_malformed_entry_is_skipped_not_fatal(self) -> None:
        methods = SettingsShippingMethodReader().available_for("ir-main")
        assert [m.code.value for m in methods] == ["ok"]


class TestGet:
    @override_settings(SHIPPING_METHODS=_VALID)
    def test_resolves_a_method_by_code_case_insensitively(self) -> None:
        method = SettingsShippingMethodReader().get("ir-main", "EXPRESS")
        assert method is not None
        assert method.code.value == "express"

    @override_settings(SHIPPING_METHODS=_VALID)
    def test_an_unknown_code_is_none(self) -> None:
        assert SettingsShippingMethodReader().get("ir-main", "drone") is None

    @override_settings(SHIPPING_METHODS=_VALID)
    def test_a_malformed_requested_code_is_none(self) -> None:
        assert SettingsShippingMethodReader().get("ir-main", "not a code!") is None
