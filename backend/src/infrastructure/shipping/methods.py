"""The per-channel shipping-method directory, backed by Django settings.

Flat-rate shipping is configuration, not shopper data, so -- like the card-to-card
destination -- the offered methods live in Django settings rather than a table in this
slice (a later slice moves rates to an admin-managed model behind this same port, without
the domain noticing). Keyed by channel slug:

    SHIPPING_METHODS = {
        "<slug>": [
            {"code": "standard", "name": "...", "price": "50000",
             "currency": "IRR", "min_days": 3, "max_days": 5,
             "zone_rates": {"tehran": "30000"}},   # optional per-zone overrides
            ...
        ],
    }
    SHIPPING_ZONES = {
        "<slug>": [
            {"code": "tehran", "name": "...", "provinces": ["تهران"]},
            ...
        ],
    }

A method's price is resolved for the destination's zone: if the destination's province
falls in a configured zone and the method has a ``zone_rates`` override for it, that rate
is used; otherwise the method's default ``price`` applies. A malformed method or zone entry
is skipped (logged, not shown) rather than crashing the checkout chooser, exactly as a
partially-configured card-to-card entry is treated as absent.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from django.conf import settings

from src.application.shipping.ports import ShippingMethodReader
from src.domain.shipping.entities import ShippingMethod, ShippingZone
from src.domain.shipping.exceptions import ShippingError
from src.domain.shipping.services import resolve_zone
from src.domain.shipping.value_objects import (
    Destination,
    Money,
    ShippingMethodCode,
    ShippingZoneCode,
    ZonedRate,
)

logger = structlog.get_logger(__name__)


class SettingsShippingMethodReader(ShippingMethodReader):
    """Resolve a channel's shipping methods (with zoned rates) from Django settings."""

    def available_for(
        self, channel: str, destination: Destination | None = None
    ) -> tuple[ShippingMethod, ...]:
        zone = self._zone_for(channel, destination)
        configured = getattr(settings, "SHIPPING_METHODS", {}).get(channel, [])
        methods: list[ShippingMethod] = []
        for raw in configured:
            method = self._to_method(raw, channel, zone)
            if method is not None:
                methods.append(method)
        return tuple(methods)

    def get(
        self, channel: str, code: str, destination: Destination | None = None
    ) -> ShippingMethod | None:
        # Normalise the requested code the same way the value object does, so a caller's
        # casing/whitespace still matches a configured entry.
        try:
            wanted = ShippingMethodCode(code).value
        except ShippingError:
            return None
        for method in self.available_for(channel, destination):
            if method.code.value == wanted:
                return method
        return None

    def _zone_for(self, channel: str, destination: Destination | None) -> ShippingZone | None:
        """Resolve which configured zone the destination falls into (``None`` if none)."""
        if destination is None:
            return None
        return resolve_zone(destination.province, self._zones(channel))

    def _zones(self, channel: str) -> tuple[ShippingZone, ...]:
        configured = getattr(settings, "SHIPPING_ZONES", {}).get(channel, [])
        zones: list[ShippingZone] = []
        for raw in configured:
            zone = self._to_zone(raw, channel)
            if zone is not None:
                zones.append(zone)
        return tuple(zones)

    @staticmethod
    def _to_zone(raw: dict[str, Any], channel: str) -> ShippingZone | None:
        """Build a domain zone from a config entry, or ``None`` if it is malformed."""
        try:
            return ShippingZone(
                code=ShippingZoneCode(raw["code"]),
                name=raw["name"],
                provinces=frozenset(raw["provinces"]),
            )
        except (KeyError, TypeError, ValueError, ShippingError):
            logger.warning("shipping_zone_misconfigured", channel=channel, code=raw.get("code"))
            return None

    @staticmethod
    def _to_method(
        raw: dict[str, Any], channel: str, zone: ShippingZone | None
    ) -> ShippingMethod | None:
        """Build a domain method with its zone-resolved price, or ``None`` if malformed."""
        try:
            currency = raw["currency"]
            rate = ZonedRate(
                default=Money(Decimal(str(raw["price"])), currency),
                by_zone={
                    ShippingZoneCode(zone_code).value: Money(Decimal(str(amount)), currency)
                    for zone_code, amount in raw.get("zone_rates", {}).items()
                },
            )
            price = rate.for_zone(zone.code.value if zone is not None else None)
            return ShippingMethod(
                code=ShippingMethodCode(raw["code"]),
                name=raw["name"],
                price=price,
                min_days=int(raw["min_days"]),
                max_days=int(raw["max_days"]),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, ShippingError):
            # A misconfigured method must not take down the whole chooser; drop it and warn.
            logger.warning("shipping_method_misconfigured", channel=channel, code=raw.get("code"))
            return None
