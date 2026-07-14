"""Tax use cases (interactors).

Two thin operations over the ``TaxRateReader`` port: read a channel's tax rate (for the
storefront to show "prices include X% VAT"), and calculate the tax due on a taxable amount
(so checkout can capture it onto an order). Dependencies arrive by constructor injection;
the source of the rate is invisible here.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.tax.ports import TaxRateReader
from src.domain.tax.services import calculate_tax
from src.domain.tax.value_objects import Money, TaxRate

logger = structlog.get_logger(__name__)


class GetTaxRate:
    """Read the tax rate a channel levies for a class (``None`` when that class is untaxed)."""

    def __init__(self, reader: TaxRateReader) -> None:
        self._reader = reader

    def execute(self, *, channel: str, tax_class: str = "standard") -> TaxRate | None:
        rate = self._reader.rate_for(channel, tax_class)
        logger.debug(
            "tax_rate_read", channel=channel, tax_class=tax_class, configured=rate is not None
        )
        return rate


@dataclass(frozen=True)
class TaxResult:
    """The tax due on a taxable amount: the applied rate and the computed amount."""

    rate: TaxRate
    amount: Money


class CalculateTax:
    """Compute the tax due on a taxable amount in a channel.

    Returns ``None`` when the channel levies no tax (so the caller captures no tax line);
    otherwise the applied rate and the rounded amount. Used by the order context's bridge to
    capture tax onto an order at checkout.
    """

    def __init__(self, reader: TaxRateReader) -> None:
        self._reader = reader

    def execute(
        self, *, channel: str, taxable: Money, tax_class: str = "standard"
    ) -> TaxResult | None:
        rate = self._reader.rate_for(channel, tax_class)
        if rate is None:
            return None
        amount = calculate_tax(taxable, rate)
        logger.debug("tax_calculated", channel=channel, tax_class=tax_class, rate=str(rate.value))
        return TaxResult(rate=rate, amount=amount)
