"""Integration tests for the settings-backed shipping method reader."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

from src.domain.shipping.value_objects import Destination
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


_ZONED = {
    "ir-main": [
        {
            "code": "standard",
            "name": "Standard post",
            "price": "50000",
            "currency": "IRR",
            "min_days": 3,
            "max_days": 5,
            "zone_rates": {"tehran": "30000"},
        },
        {
            "code": "free",
            "name": "Free",
            "price": "0",
            "currency": "IRR",
            "min_days": 5,
            "max_days": 7,
        },
    ],
}
_ZONES = {"ir-main": [{"code": "tehran", "name": "Tehran", "provinces": ["تهران"]}]}


class TestZonedRates:
    @override_settings(SHIPPING_METHODS=_ZONED, SHIPPING_ZONES=_ZONES)
    def test_a_destination_in_a_zone_gets_the_zone_rate(self) -> None:
        methods = SettingsShippingMethodReader().available_for(
            "ir-main", Destination(province="تهران")
        )
        standard = next(m for m in methods if m.code.value == "standard")
        assert standard.price.amount == Decimal("30000")

    @override_settings(SHIPPING_METHODS=_ZONED, SHIPPING_ZONES=_ZONES)
    def test_a_destination_outside_every_zone_gets_the_default_rate(self) -> None:
        methods = SettingsShippingMethodReader().available_for(
            "ir-main", Destination(province="اصفهان")
        )
        standard = next(m for m in methods if m.code.value == "standard")
        assert standard.price.amount == Decimal("50000")

    @override_settings(SHIPPING_METHODS=_ZONED, SHIPPING_ZONES=_ZONES)
    def test_no_destination_lists_default_rates(self) -> None:
        methods = SettingsShippingMethodReader().available_for("ir-main")
        standard = next(m for m in methods if m.code.value == "standard")
        assert standard.price.amount == Decimal("50000")

    @override_settings(SHIPPING_METHODS=_ZONED, SHIPPING_ZONES=_ZONES)
    def test_a_method_without_a_zone_override_keeps_its_price_in_a_zone(self) -> None:
        # "free" has no zone_rates, so it stays 0 even for a Tehran destination.
        methods = SettingsShippingMethodReader().available_for(
            "ir-main", Destination(province="تهران")
        )
        free = next(m for m in methods if m.code.value == "free")
        assert free.price.amount == Decimal("0")

    @override_settings(SHIPPING_METHODS=_ZONED, SHIPPING_ZONES=_ZONES)
    def test_get_resolves_the_zone_rate_for_a_destination(self) -> None:
        method = SettingsShippingMethodReader().get(
            "ir-main", "standard", Destination(province="تهران")
        )
        assert method is not None
        assert method.price.amount == Decimal("30000")

    @override_settings(
        SHIPPING_METHODS=_ZONED,
        SHIPPING_ZONES={"ir-main": [{"code": "broken"}]},  # malformed zone -> skipped
    )
    def test_a_malformed_zone_is_skipped_and_falls_back_to_default_rates(self) -> None:
        methods = SettingsShippingMethodReader().available_for(
            "ir-main", Destination(province="تهران")
        )
        standard = next(m for m in methods if m.code.value == "standard")
        assert standard.price.amount == Decimal("50000")
