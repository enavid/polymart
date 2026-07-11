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
