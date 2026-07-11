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
from src.domain.shipping.value_objects import Money, ShippingMethodCode, ShippingZoneCode

_NAME_MAX_LENGTH = 120
# A sane upper bound so a mis-configured window (e.g. 99999 days) fails at the domain edge.
_MAX_DELIVERY_DAYS = 365


@dataclass(frozen=True)
class ShippingMethod:
    """A flat-rate delivery option offered in a channel.

    ``min_days``/``max_days`` describe the estimated delivery window shown to the shopper;
    they are non-negative and ordered (``min_days <= max_days``). ``price`` is the flat cost
    added to the order total when this method is chosen.
    """

    code: ShippingMethodCode
    name: str
    price: Money
    min_days: int
    max_days: int

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidShippingMethodError(f"name: {self.name!r}")
        object.__setattr__(self, "name", name)
        self._validate_window()

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
    """A named set of provinces that share a shipping rate.

    A method's per-zone override is keyed by this zone's ``code``; ``covers`` matches a
    destination's province case- and whitespace-insensitively (so "  Tehran " and "tehran"
    are the same place). A zone must cover at least one non-blank province -- a zone that
    matches nothing is a misconfiguration.
    """

    code: ShippingZoneCode
    name: str
    provinces: frozenset[str]

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidShippingZoneError(f"name: {self.name!r}")
        object.__setattr__(self, "name", name)

        trimmed = frozenset(province.strip() for province in self.provinces)
        if not trimmed or "" in trimmed:
            raise InvalidShippingZoneError(f"provinces: {self.provinces!r}")
        object.__setattr__(self, "provinces", trimmed)

    def covers(self, province: str) -> bool:
        key = province.strip().casefold()
        return any(configured.casefold() == key for configured in self.provinces)
