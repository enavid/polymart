"""Ports (interfaces) for the inventory context.

The application layer depends only on these abstractions; infrastructure supplies the
adapters. The repository owns the atomic, row-locked read-modify-write for stock
movements -- reserving, releasing, and adjusting physical on-hand -- so concurrent
checkouts on the last unit serialize and cannot both reserve it (the anti-overselling
guarantee lives at the stock-level row).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.inventory.entities import StockLevel, StockPolicy, StockSource
from src.domain.inventory.value_objects import StockSourceCode


class StockLevelRepository(ABC):
    """Persistence boundary for a variant's per-source stock levels.

    Reads return domain ``StockLevel`` objects. The mutating methods each run their
    whole read-modify-write under a row lock inside a transaction, so two concurrent
    reservations cannot both read the same available amount and oversell.
    """

    @abstractmethod
    def levels_for(self, sku: str) -> list[StockLevel]:
        """Return the variant's stock levels across all sources (unlocked read)."""

    @abstractmethod
    def reserve(self, sku: str, quantity: int) -> None:
        """Atomically reserve ``quantity`` units across the variant's sources.

        Locks the level rows, plans the reservation (most-available-first), and applies
        it. Raises ``InsufficientStockError`` (before any movement) if available-to-promise
        is short.
        """

    @abstractmethod
    def release(self, sku: str, quantity: int) -> None:
        """Atomically release ``quantity`` reserved units (most-reserved-first)."""

    @abstractmethod
    def set_on_hand(self, sku: str, source_code: StockSourceCode, quantity: int) -> int:
        """Set the physical on-hand count at one source; return the new on-hand count."""

    @abstractmethod
    def adjust_on_hand(self, sku: str, source_code: StockSourceCode, delta: int) -> int:
        """Apply a signed delta to the physical on-hand at one source; return the new count."""

    @abstractmethod
    def on_hand_at(self, sku: str, source_code: StockSourceCode) -> int:
        """Return the physical on-hand count at one source (0 if no level row exists)."""

    @abstractmethod
    def total_on_hand(self, sku: str) -> int:
        """Return the physical on-hand count summed across all sources."""

    @abstractmethod
    def available_for_skus(self, skus: Sequence[str]) -> dict[str, int]:
        """Return available-to-promise (on-hand minus reserved) per sku, batched."""


class StockSourceRepository(ABC):
    """Persistence boundary for stock sources (warehouses)."""

    @abstractmethod
    def ensure_default(self) -> StockSourceCode:
        """Ensure the default stock source exists and return its code."""

    @abstractmethod
    def exists(self, code: StockSourceCode) -> bool:
        """Return whether a source with this code exists."""

    @abstractmethod
    def add(self, source: StockSource) -> StockSource:
        """Persist a new stock source; raise ``StockSourceAlreadyExistsError`` on a
        duplicate code. Returns the stored source carrying its assigned id."""

    @abstractmethod
    def list_all(self) -> list[StockSource]:
        """Return every stock source, ordered by code."""

    @abstractmethod
    def get(self, code: StockSourceCode) -> StockSource:
        """Return the source with this code (carrying its id); raise
        ``StockSourceNotFoundError`` if none exists."""


class StockPolicyRepository(ABC):
    """Persistence boundary for per-variant selling policy (backorder + low-stock)."""

    @abstractmethod
    def get(self, sku: str) -> StockPolicy:
        """Return the variant's policy, or the default (no backorder, no alert) if unset."""

    @abstractmethod
    def set_policy(self, sku: str, *, backorderable: bool, low_stock_threshold: int) -> StockPolicy:
        """Create or update a variant's policy (preserving any backordered count)."""

    @abstractmethod
    def backorderable_skus(self, skus: Sequence[str]) -> set[str]:
        """Return the subset of ``skus`` flagged backorderable (buyable past on-hand)."""
