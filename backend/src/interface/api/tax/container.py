"""Composition root for the tax slice.

The only place that wires the concrete settings-backed reader into the tax use cases. Views
depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.tax.use_cases import GetTaxRate
from src.infrastructure.tax.rates import SettingsTaxRateReader


def build_get_tax_rate() -> GetTaxRate:
    return GetTaxRate(SettingsTaxRateReader())
