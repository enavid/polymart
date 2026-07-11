"""The per-channel shipping-method directory, backed by Django settings.

Flat-rate shipping is configuration, not shopper data, so -- like the card-to-card
destination -- the offered methods live in Django settings rather than a table in this
first slice (a later slice moves rates to an admin-managed model behind this same port,
without the domain noticing). Keyed by channel slug:

    SHIPPING_METHODS = {
        "<slug>": [
            {"code": "standard", "name": "...", "price": "50000",
             "currency": "IRR", "min_days": 3, "max_days": 5},
            ...
        ],
    }

A malformed entry is skipped (logged, not shown) rather than crashing the checkout
chooser, exactly as a partially-configured card-to-card entry is treated as absent.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from django.conf import settings

from src.application.shipping.ports import ShippingMethodReader
from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.exceptions import ShippingError
from src.domain.shipping.value_objects import Money, ShippingMethodCode

logger = structlog.get_logger(__name__)


class SettingsShippingMethodReader(ShippingMethodReader):
    """Resolve a channel's shipping methods from the ``SHIPPING_METHODS`` setting."""

    def available_for(self, channel: str) -> tuple[ShippingMethod, ...]:
        configured = getattr(settings, "SHIPPING_METHODS", {}).get(channel, [])
        methods: list[ShippingMethod] = []
        for raw in configured:
            method = self._to_method(raw, channel)
            if method is not None:
                methods.append(method)
        return tuple(methods)

    def get(self, channel: str, code: str) -> ShippingMethod | None:
        # Normalise the requested code the same way the value object does, so a caller's
        # casing/whitespace still matches a configured entry.
        try:
            wanted = ShippingMethodCode(code).value
        except ShippingError:
            return None
        for method in self.available_for(channel):
            if method.code.value == wanted:
                return method
        return None

    @staticmethod
    def _to_method(raw: dict[str, Any], channel: str) -> ShippingMethod | None:
        """Build a domain method from a config entry, or ``None`` if it is malformed."""
        try:
            return ShippingMethod(
                code=ShippingMethodCode(raw["code"]),
                name=raw["name"],
                price=Money(Decimal(str(raw["price"])), raw["currency"]),
                min_days=int(raw["min_days"]),
                max_days=int(raw["max_days"]),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, ShippingError):
            # A misconfigured method must not take down the whole chooser; drop it and warn.
            logger.warning("shipping_method_misconfigured", channel=channel, code=raw.get("code"))
            return None
