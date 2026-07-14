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
    """Resolve a channel's tax rate per tax class from Django settings.

    ``TAX_CLASSES`` maps a class code to a rate string per channel::

        TAX_CLASSES = {"ir-main": {"standard": "9", "reduced": "5"}}

    A class present in the map uses that rate (0 is a valid taxed-at-zero rate). The
    ``standard`` class falls back to the legacy single ``TAX_RATES[channel]`` rate when it is
    not in ``TAX_CLASSES``; any *other* class the channel does not map (an exempt class) levies
    no tax. A malformed rate is treated as untaxed (logged), never crashing checkout.
    """

    def rate_for(self, channel: str, tax_class: str = "standard") -> TaxRate | None:
        classes = getattr(settings, "TAX_CLASSES", {}).get(channel, {})
        if tax_class in classes:
            configured: object | None = classes[tax_class]
        elif tax_class == "standard":
            # Backward-compatible fallback: the single channel rate is the standard class.
            configured = getattr(settings, "TAX_RATES", {}).get(channel)
        else:
            # An unmapped, non-standard class is exempt (no tax).
            return None
        if configured is None:
            return None
        try:
            return TaxRate(Decimal(str(configured)))
        except (TypeError, ValueError, InvalidOperation, TaxError):
            # A misconfigured rate must not take down checkout; treat the class as untaxed.
            logger.warning("tax_rate_misconfigured", channel=channel, tax_class=tax_class)
            return None
