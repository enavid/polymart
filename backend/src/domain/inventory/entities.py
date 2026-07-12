"""Entities for the inventory context.

A ``StockSource`` is a warehouse/location that holds stock. A ``StockLevel`` is the stock
of one variant at one source: a physical ``on_hand`` count and a ``reserved`` count held
against open orders. The sellable amount is ``available = on_hand - reserved``; the
invariant ``0 <= reserved <= on_hand`` is enforced at construction so a level can never
represent more reserved than exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.inventory.exceptions import (
    InvalidStockLevelError,
    InvalidStockPolicyError,
    InvalidStockSourceError,
)
from src.domain.inventory.value_objects import Quantity, StockSourceCode

_SOURCE_NAME_MAX_LENGTH = 100
# A shared zero quantity for defaults: Quantity is frozen/immutable, so one instance is
# safe to reuse (and satisfies the "no function call in a dataclass default" lint).
_ZERO = Quantity(0)


@dataclass(frozen=True)
class StockSource:
    """A location (warehouse) that holds physical stock.

    ``id`` is the persistence identity (``None`` before the row is created); it is the
    handle the access layer scopes a per-source management grant to.
    """

    code: StockSourceCode
    name: str
    id: int | None = None

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or len(name) > _SOURCE_NAME_MAX_LENGTH:
            raise InvalidStockSourceError(f"invalid stock source name: {self.name!r}")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True)
class StockLevel:
    """The stock of one variant (``sku``) at one ``source``.

    ``on_hand`` is the physical count; ``reserved`` is held against open orders. The
    difference is the sellable ``available`` amount, and reservations can never exceed
    the physical count.
    """

    sku: str
    source_code: StockSourceCode
    on_hand: Quantity
    reserved: Quantity

    def __post_init__(self) -> None:
        if self.reserved.value > self.on_hand.value:
            raise InvalidStockLevelError(
                f"reserved {self.reserved.value} exceeds on_hand {self.on_hand.value} "
                f"for {self.sku} at {self.source_code}"
            )

    @property
    def available(self) -> int:
        """Sellable units at this source: physical stock not yet reserved."""
        return self.on_hand.value - self.reserved.value


@dataclass(frozen=True)
class StockPolicy:
    """Per-variant (``sku``) selling policy the physical levels cannot express.

    ``backorderable`` lets a variant be ordered beyond its physical available-to-promise:
    the overflow is tracked as ``backordered`` (a promise with no physical backing yet),
    which is why the level invariant ``reserved <= on_hand`` can stay intact -- backorder
    never violates it. ``low_stock_threshold`` is the available count at or below which a
    low-stock alert is emitted (0 disables the alert).
    """

    sku: str
    backorderable: bool = False
    low_stock_threshold: int = 0
    backordered: Quantity = _ZERO

    def __post_init__(self) -> None:
        if self.low_stock_threshold < 0:
            raise InvalidStockPolicyError(
                f"low_stock_threshold must be non-negative, got {self.low_stock_threshold}"
            )

    @property
    def has_backorder(self) -> bool:
        """Whether units are currently promised beyond physical stock."""
        return self.backordered.value > 0
