"""Ports (interfaces) for the address use cases.

The application layer depends only on these abstractions; concrete adapters (Django
ORM, a real clock, a secure id generator, in-memory fakes) live elsewhere and are
injected at the composition root, keeping the dependency rule pointing inward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.address.entities import Address
from src.domain.address.value_objects import AddressId


class AddressRepository(ABC):
    """Persistence boundary for the Address aggregate.

    Reads are always scoped to the owner, so one shopper can never resolve another's
    address (there is no un-scoped ``get`` by id).
    """

    @abstractmethod
    def add(self, address: Address) -> Address:
        """Persist a new address and return it.

        If ``address.is_default`` is set, any other default address the owner already
        has is atomically unset first, so an owner never ends up with two defaults.
        """

    @abstractmethod
    def list_for_owner(self, owner: str) -> tuple[Address, ...]:
        """Return all of the owner's addresses (default first, newest first)."""

    @abstractmethod
    def get_for_owner(self, owner: str, address_id: str) -> Address:
        """Return the owner's address by id, or raise ``AddressNotFoundError``."""

    @abstractmethod
    def update(self, address: Address) -> Address:
        """Persist an already-loaded address's mutable fields (not id/owner/default)."""

    @abstractmethod
    def delete(self, owner: str, address_id: str) -> None:
        """Delete the owner's address, or raise ``AddressNotFoundError``."""

    @abstractmethod
    def set_default(self, owner: str, address_id: str) -> Address:
        """Make the owner's address the sole default, atomically unsetting any other."""

    @abstractmethod
    def count_for_owner(self, owner: str) -> int:
        """Return how many addresses the owner has saved (enforces the per-owner cap)."""


class AddressIdGenerator(ABC):
    """Source of a fresh, unguessable address id, injected so it is deterministic in tests."""

    @abstractmethod
    def next(self) -> AddressId:
        """Return a new address id."""


class Clock(ABC):
    """Source of the current time, injected so ``created_at`` is testable.

    The address context owns its own ``Clock`` port (the dependency rule keeps
    contexts decoupled); the trivial system adapter lives in infrastructure.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""
