"""Value objects for the inventory context.

Value objects are immutable and self-validating: an instance cannot exist in an invalid
state, and equality is by value. The inventory context owns its own ``Quantity`` rather
than importing the catalog's ``StockQuantity`` -- a bounded context depends on narrow
abstractions of its neighbours, never on their domain types.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.inventory.exceptions import (
    InvalidQuantityError,
    InvalidStockSourceCodeError,
)

# A quantity is a non-negative integer bounded to the stored column's range (a signed
# 32-bit integer), mirroring the catalog's stock bound so a level round-trips losslessly.
_QUANTITY_MAX = 2_147_483_647

# A source code is lower-case kebab-case ("main", "tehran-dc") -- the stable key a level
# row and any config reference.
_CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CODE_MAX_LENGTH = 32


@dataclass(frozen=True)
class Quantity:
    """A non-negative, bounded count of stock units.

    Zero is valid (an out-of-stock or unreserved state). A negative value or one past
    the stored maximum is rejected at construction so arithmetic downstream is safe.
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidQuantityError(self.value)
        if self.value < 0 or self.value > _QUANTITY_MAX:
            raise InvalidQuantityError(self.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class StockSourceCode:
    """The stable, lower-case identifier of a stock source (warehouse) within the store."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if len(normalized) > _CODE_MAX_LENGTH or not _CODE_RE.match(normalized):
            raise InvalidStockSourceCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
