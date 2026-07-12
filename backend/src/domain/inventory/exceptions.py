"""Domain exceptions for the inventory context.

A single base (``InventoryError``) lets a caller catch the whole family; the specific
subclasses carry the meaning a use case or transport needs. Pure Python -- no framework.
"""

from __future__ import annotations


class InventoryError(Exception):
    """Base class for every inventory-domain error."""


class InvalidQuantityError(InventoryError):
    """Raised when a quantity is not a non-negative integer within bounds."""

    def __init__(self, value: object) -> None:
        super().__init__(f"invalid quantity: {value!r}")
        self.value = value


class InvalidStockSourceCodeError(InventoryError):
    """Raised when a stock-source code is structurally malformed."""

    def __init__(self, value: object) -> None:
        super().__init__(f"invalid stock source code: {value!r}")
        self.value = value


class InvalidStockSourceError(InventoryError):
    """Raised when a stock source's name is invalid."""


class InvalidStockLevelError(InventoryError):
    """Raised when a stock level violates its invariant (0 <= reserved <= on_hand)."""


class InvalidStockPolicyError(InventoryError):
    """Raised when a stock policy is invalid (e.g. a negative low-stock threshold)."""


class InsufficientStockError(InventoryError):
    """Raised when a reservation cannot be satisfied from available stock.

    This is the overselling guard: a variant's available-to-promise (on-hand minus
    reserved, summed across sources) can never be exceeded, so a reservation larger
    than what is available is refused *before any movement* rather than partially
    applied.
    """

    def __init__(self, *, sku: str, requested: int, available: int) -> None:
        super().__init__(
            f"insufficient stock for {sku}: requested {requested}, available {available}"
        )
        self.sku = sku
        self.requested = requested
        self.available = available


class StockSourceNotFoundError(InventoryError):
    """Raised when a stock source referenced by code does not exist."""

    def __init__(self, code: str) -> None:
        super().__init__(f"stock source not found: {code}")
        self.code = code


class StockSourceAlreadyExistsError(InventoryError):
    """Raised when creating a stock source whose code is already taken."""

    def __init__(self, code: str) -> None:
        super().__init__(f"stock source already exists: {code}")
        self.code = code
