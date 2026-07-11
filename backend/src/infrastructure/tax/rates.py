"""The per-channel tax-rate directory, backed by Django settings.

The channel VAT rate is configuration, not shopper data, so -- like the shipping methods and
the card-to-card destination -- it lives in Django settings rather than a table in this
slice (a later slice moves rates to an admin-managed model, and tax classes/zones plug in,
behind this same port without the domain noticing). Keyed by channel slug, the value is the
percentage rate as a string (so the exact ``Decimal`` survives):

    TAX_RATES = {"ir-main": "9"}

A channel absent from the map (or a malformed entry) levies no tax: ``rate_for`` returns
``None`` (logged for a malformed value), exactly as a partially-configured shipping method is
treated as absent rather than crashing checkout.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import structlog
from django.conf import settings

from src.application.tax.ports import TaxRateReader
from src.domain.tax.exceptions import TaxError
from src.domain.tax.value_objects import TaxRate

logger = structlog.get_logger(__name__)


class SettingsTaxRateReader(TaxRateReader):
    """Resolve a channel's tax rate from the ``TAX_RATES`` Django setting."""

    def rate_for(self, channel: str) -> TaxRate | None:
        configured = getattr(settings, "TAX_RATES", {}).get(channel)
        if configured is None:
            return None
        try:
            return TaxRate(Decimal(str(configured)))
        except (TypeError, ValueError, InvalidOperation, TaxError):
            # A misconfigured rate must not take down checkout; treat the channel as untaxed.
            logger.warning("tax_rate_misconfigured", channel=channel)
            return None
