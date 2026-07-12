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
    WeightBracket,
    WeightTable,
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
        """Resolve which configured zone the destination falls into (``None`` if none).

        The destination's province is first mapped through the channel's alias table (so a
        Latin "Tehran" resolves to the same zone as "تهران"), then matched against the zones
        (province + optional city).
        """
        if destination is None:
            return None
        canonical = self._canonical_destination(channel, destination)
        return resolve_zone(canonical, self._zones(channel))

    def _canonical_destination(self, channel: str, destination: Destination) -> Destination:
        """Apply the channel's province-alias table, returning a possibly-rewritten destination.

        ``SHIPPING_PROVINCE_ALIASES[channel]`` maps an input province (any casing) to the
        canonical province a zone is configured under. An unknown province is left unchanged.
        """
        aliases = getattr(settings, "SHIPPING_PROVINCE_ALIASES", {}).get(channel, {})
        folded = {str(k).strip().casefold(): str(v) for k, v in aliases.items()}
        canonical_province = folded.get(destination.province.casefold())
        if canonical_province is None:
            return destination
        return Destination(province=canonical_province, city=destination.city)

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
        """Build a domain zone from a config entry, or ``None`` if it is malformed.

        A zone may narrow to specific ``cities`` (optional); an entry omitting them covers the
        whole province.
        """
        try:
            return ShippingZone(
                code=ShippingZoneCode(raw["code"]),
                name=raw["name"],
                provinces=frozenset(raw["provinces"]),
                cities=frozenset(raw.get("cities", [])),
            )
        except (KeyError, TypeError, ValueError, ShippingError):
            logger.warning("shipping_zone_misconfigured", channel=channel, code=raw.get("code"))
            return None

    @staticmethod
    def _to_method(
        raw: dict[str, Any], channel: str, zone: ShippingZone | None
    ) -> ShippingMethod | None:
        """Build a domain method with its zone-resolved price, or ``None`` if malformed.

        A method is priced either by a flat/zoned rate (``price`` + optional ``zone_rates``) or
        by a weight table (``weight_brackets``); configuring both on one method is a bug and is
        rejected (skipped + logged). A weight method's displayed ``price`` is its lightest
        bracket; its actual cost is resolved from the order weight at quote time.
        """
        try:
            currency = raw["currency"]
            weight_brackets = raw.get("weight_brackets")
            if weight_brackets is not None:
                if raw.get("zone_rates"):
                    raise ShippingError("a method cannot mix zone_rates and weight_brackets")
                table = _to_weight_table(weight_brackets, currency)
                price = table.from_price
            else:
                table = None
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
                # Optional; a method omitting the flag is a normal delivery method.
                is_pickup=bool(raw.get("pickup", False)),
                weight_table=table,
            )
        except (KeyError, TypeError, ValueError, InvalidOperation, ShippingError):
            # A misconfigured method must not take down the whole chooser; drop it and warn.
            logger.warning("shipping_method_misconfigured", channel=channel, code=raw.get("code"))
            return None


def _to_weight_table(raw_brackets: object, currency: str) -> WeightTable:
    """Build a WeightTable from a config list of ``{"up_to_grams": int|None, "price": str}``.

    Ordering/overflow/currency validity is enforced by ``WeightTable`` at construction; a
    malformed table raises (caught by the caller, which skips and logs the method).
    """
    if not isinstance(raw_brackets, list):
        raise ShippingError("weight_brackets must be a list")
    brackets = tuple(
        WeightBracket(
            up_to_grams=row.get("up_to_grams"),
            price=Money(Decimal(str(row["price"])), currency),
        )
        for row in raw_brackets
    )
    return WeightTable(brackets=brackets)
