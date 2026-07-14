"""Integration tests for the settings-backed tax-rate reader."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pytest_django.fixtures import SettingsWrapper

from src.domain.tax.value_objects import TaxRate
from src.infrastructure.tax.rates import SettingsTaxRateReader

pytestmark = pytest.mark.integration


class TestSettingsTaxRateReader:
    def test_reads_a_configured_rate(self, settings: SettingsWrapper) -> None:
        settings.TAX_RATES = {"ir-main": "9"}
        assert SettingsTaxRateReader().rate_for("ir-main") == TaxRate(Decimal("9"))

    def test_reads_a_fractional_rate(self, settings: SettingsWrapper) -> None:
        settings.TAX_RATES = {"ir-main": "9.5"}
        assert SettingsTaxRateReader().rate_for("ir-main") == TaxRate(Decimal("9.5"))

    def test_an_unconfigured_channel_levies_no_tax(self, settings: SettingsWrapper) -> None:
        settings.TAX_RATES = {"ir-main": "9"}
        assert SettingsTaxRateReader().rate_for("ghost") is None

    def test_no_config_at_all_levies_no_tax(self, settings: SettingsWrapper) -> None:
        settings.TAX_RATES = {}
        assert SettingsTaxRateReader().rate_for("ir-main") is None

    @pytest.mark.parametrize("bad", ["not-a-number", "-1", "150", {"rate": "9"}, None])
    def test_a_malformed_rate_degrades_to_untaxed(
        self, settings: SettingsWrapper, bad: object
    ) -> None:
        settings.TAX_RATES = {"ir-main": bad}
        assert SettingsTaxRateReader().rate_for("ir-main") is None


class TestTaxClasses:
    def test_a_configured_class_uses_its_rate(self, settings) -> None:  # type: ignore[no-untyped-def]
        settings.TAX_CLASSES = {"ir-main": {"standard": "9", "reduced": "5"}}
        assert SettingsTaxRateReader().rate_for("ir-main", "reduced") == TaxRate(Decimal("5"))
        assert SettingsTaxRateReader().rate_for("ir-main", "standard") == TaxRate(Decimal("9"))

    def test_standard_falls_back_to_the_legacy_channel_rate(self, settings) -> None:  # type: ignore[no-untyped-def]
        settings.TAX_CLASSES = {}
        settings.TAX_RATES = {"ir-main": "9"}
        assert SettingsTaxRateReader().rate_for("ir-main", "standard") == TaxRate(Decimal("9"))
        assert SettingsTaxRateReader().rate_for("ir-main") == TaxRate(Decimal("9"))

    def test_an_unmapped_non_standard_class_is_exempt(self, settings) -> None:  # type: ignore[no-untyped-def]
        settings.TAX_CLASSES = {"ir-main": {"standard": "9"}}
        settings.TAX_RATES = {"ir-main": "9"}
        # "exempt" (any unmapped, non-standard class) levies no tax.
        assert SettingsTaxRateReader().rate_for("ir-main", "exempt") is None

    def test_a_class_configured_at_zero_is_taxed_at_zero_not_exempt(self, settings) -> None:  # type: ignore[no-untyped-def]
        settings.TAX_CLASSES = {"ir-main": {"zero": "0"}}
        # A configured 0 rate is a real (taxed-at-zero) rate, distinct from an unmapped class.
        assert SettingsTaxRateReader().rate_for("ir-main", "zero") == TaxRate(Decimal("0"))

    def test_a_malformed_class_rate_degrades_to_untaxed(self, settings) -> None:  # type: ignore[no-untyped-def]
        settings.TAX_CLASSES = {"ir-main": {"reduced": "not-a-number"}}
        assert SettingsTaxRateReader().rate_for("ir-main", "reduced") is None
