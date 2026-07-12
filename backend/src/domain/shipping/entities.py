"""Entities for the shipping context.

A ``ShippingMethod`` is one delivery option a channel offers: a stable code, a
human-readable name, a flat price, and an estimated delivery window (in days). It is
read-only configuration in this slice -- the storefront lists methods and checkout quotes
one -- so the entity owns only its own validity, not any lifecycle.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.shipping.exceptions import (
    InvalidShippingMethodError,
    InvalidShippingZoneError,
)
from src.domain.shipping.value_objects import (
    Destination,
    Money,
    ShippingMethodCode,
    ShippingZoneCode,
    WeightTable,
)

_NAME_MAX_LENGTH = 120
# A sane upper bound so a mis-configured window (e.g. 99999 days) fails at the domain edge.
_MAX_DELIVERY_DAYS = 365


@dataclass(frozen=True)
class ShippingMethod:
    """A flat-rate delivery option offered in a channel.

    ``min_days``/``max_days`` describe the estimated delivery window shown to the shopper;
    they are non-negative and ordered (``min_days <= max_days``). ``price`` is the flat cost
    added to the order total when this method is chosen. ``is_pickup`` marks a BOPIS
    (in-store/local pickup) option: it captures no shipping address and follows the
    ready-for-pickup -> picked-up fulfilment path instead of shipping.
    """

    code: ShippingMethodCode
    name: str
    price: Money
    min_days: int
    max_days: int
    is_pickup: bool = False
    # When set, the method is weight-priced: ``price`` is the indicative "from" price (the
    # lightest bracket) for browsing, and ``quote`` resolves the actual cost by order weight.
    # ``None`` is a flat/zoned method whose cost is always ``price``.
    weight_table: WeightTable | None = None

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidShippingMethodError(f"name: {self.name!r}")
        object.__setattr__(self, "name", name)
        self._validate_window()

    def quote(self, weight_grams: int) -> Money:
        """The cost for an order of this weight: the weight table's bracket, or the flat price."""
        if self.weight_table is not None:
            return self.weight_table.price_for(weight_grams)
        return self.price

    def _validate_window(self) -> None:
        for label, value in (("min_days", self.min_days), ("max_days", self.max_days)):
            # bool is an int subclass; reject it so True/False never become a day count.
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidShippingMethodError(f"{label} must be an int: {value!r}")
            if value < 0 or value > _MAX_DELIVERY_DAYS:
                raise InvalidShippingMethodError(f"{label} out of range: {value!r}")
        if self.max_days < self.min_days:
            raise InvalidShippingMethodError(
                f"max_days {self.max_days} is before min_days {self.min_days}"
            )


@dataclass(frozen=True)
class ShippingZone:
    """A named set of provinces (optionally narrowed to cities) that share a shipping rate.

    A method's per-zone override is keyed by this zone's ``code``; ``covers`` matches a
    destination's province case- and whitespace-insensitively (so "  Tehran " and "tehran"
    are the same place). When ``cities`` is non-empty the zone is *city-scoped*: it covers a
    destination only if its province matches **and** its city is one of the listed cities --
    letting a fine city zone (e.g. the capital) be ordered before a broad province zone. An
    empty ``cities`` covers the whole province. A zone must cover at least one non-blank
    province -- a zone that matches nothing is a misconfiguration.
    """

    code: ShippingZoneCode
    name: str
    provinces: frozenset[str]
    cities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidShippingZoneError(f"name: {self.name!r}")
        object.__setattr__(self, "name", name)

        trimmed = frozenset(province.strip() for province in self.provinces)
        if not trimmed or "" in trimmed:
            raise InvalidShippingZoneError(f"provinces: {self.provinces!r}")
        object.__setattr__(self, "provinces", trimmed)

        cities = frozenset(city.strip() for city in self.cities)
        if "" in cities:
            raise InvalidShippingZoneError(f"cities: {self.cities!r}")
        object.__setattr__(self, "cities", cities)

    def covers(self, destination: Destination) -> bool:
        province_key = destination.province.casefold()
        if not any(configured.casefold() == province_key for configured in self.provinces):
            return False
        if not self.cities:
            return True  # a province-wide zone covers any city in the province
        city_key = destination.city.casefold()
        return any(configured.casefold() == city_key for configured in self.cities)
