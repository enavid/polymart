"""Ports (interfaces) for the order use cases.

The application layer depends only on these abstractions; concrete adapters (Django
ORM, catalog/channel/cart bridges, a real clock and number generator, in-memory fakes)
live elsewhere and are injected at the composition root, keeping the dependency rule
pointing inward.

Several ports are *narrow* boundaries onto neighbouring bounded contexts: the order
context learns a variant's current price, a channel's currency, and a cart's contents,
and deducts/returns inventory, without depending on the catalog, channel, or cart
domains.

The ``UnitOfWork`` is the transaction boundary. Checkout must be all-or-nothing across
several aggregates (deduct stock, create the order, clear the cart, write the audit
entry); running the whole use case inside ``uow.atomic()`` makes a failure anywhere --
an oversell, say -- roll every step back, so stock is never deducted without an order
and the audit entry never records a purchase that did not commit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from src.domain.order.entities import Order
from src.domain.order.value_objects import Money, OrderNumber, OrderStatus


@dataclass(frozen=True)
class CheckoutLine:
    """One line of a cart, flattened for checkout (no cart-domain types leak here)."""

    sku: str
    quantity: int


@dataclass(frozen=True)
class OrderPage:
    """One page of a shopper's orders plus the full count (for pagination)."""

    items: tuple[Order, ...]
    total: int


class OrderRepository(ABC):
    """Persistence boundary for the Order aggregate.

    Reads are always scoped to the owner, so one shopper can never resolve another's
    order (there is no un-scoped ``get`` by number).
    """

    @abstractmethod
    def add(self, order: Order) -> Order:
        """Persist a new order (with its lines) and return it with its assigned id."""

    @abstractmethod
    def get_for_owner(self, owner: str, number: str) -> Order:
        """Return the owner's order by number, or raise ``OrderNotFoundError``."""

    @abstractmethod
    def get_for_update(self, owner: str, number: str) -> Order:
        """Return the owner's order under a row lock (for a status change).

        Locking serializes concurrent mutations of the same order so, e.g., two
        cancels cannot both read a ``pending`` order and both restock.
        """

    @abstractmethod
    def list_for_owner(
        self, owner: str, *, limit: int, offset: int
    ) -> tuple[tuple[Order, ...], int]:
        """Return one page of the owner's orders (newest first) plus the total count."""

    @abstractmethod
    def set_status(self, order: Order, status: OrderStatus) -> Order:
        """Persist a status change for an already-stored order and return it."""


class CartForCheckout(ABC):
    """Narrow boundary onto the cart context: read its contents and clear it."""

    @abstractmethod
    def line_items(self, owner: str, channel: str) -> tuple[CheckoutLine, ...]:
        """Return the owner's cart lines for the channel (empty tuple if none)."""

    @abstractmethod
    def clear(self, owner: str, channel: str) -> None:
        """Empty the owner's cart for the channel (a no-op if already empty)."""


class PricingReader(ABC):
    """Narrow read boundary onto the catalog for capturing an order line's price."""

    @abstractmethod
    def price_of(self, sku: str, channel: str) -> Money | None:
        """Return the variant's current unit price in the channel, or ``None``."""


class ChannelReader(ABC):
    """Narrow read boundary onto the channel context for the order currency."""

    @abstractmethod
    def currency_of(self, channel: str) -> str | None:
        """Return the channel's ISO 4217 currency code, or ``None`` if it does not exist."""


@dataclass(frozen=True)
class OwnedAddress:
    """A shopper's saved address, flattened for checkout (no address-domain types leak here)."""

    recipient_name: str
    phone_number: str
    province: str
    city: str
    postal_code: str
    line1: str
    line2: str | None


class AddressReader(ABC):
    """Narrow read boundary onto the address context for capturing a checkout's shipping address."""

    @abstractmethod
    def get_for_owner(self, owner: str, address_id: str) -> OwnedAddress | None:
        """Return the owner's saved address, or ``None`` if it does not exist or isn't theirs."""


class Inventory(ABC):
    """Boundary for moving on-hand stock as orders are placed and cancelled.

    ``deduct`` captures stock for a placed order and refuses an oversell; ``restock``
    returns it when an order is cancelled. Both take a row lock so concurrent moves on
    the same variant serialize instead of racing (the anti-overselling guarantee).
    """

    @abstractmethod
    def deduct(self, sku: str, quantity: int) -> None:
        """Withdraw ``quantity`` from the variant, or raise on an unknown SKU / oversell."""

    @abstractmethod
    def restock(self, sku: str, quantity: int) -> None:
        """Return ``quantity`` to the variant (the reverse of ``deduct``)."""


class OrderNumberGenerator(ABC):
    """Source of a fresh, unguessable order number, injected so it is deterministic in tests."""

    @abstractmethod
    def next(self) -> OrderNumber:
        """Return a new order number."""


class Clock(ABC):
    """Source of the current time, injected so ``placed_at`` is testable.

    The order context owns its own ``Clock`` port (the dependency rule keeps contexts
    decoupled); the trivial system adapter lives in infrastructure.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""


class UnitOfWork(ABC):
    """The transaction boundary for a multi-aggregate use case.

    ``atomic()`` returns a context manager; everything performed inside it commits
    together or rolls back together on any exception.
    """

    @abstractmethod
    def atomic(self) -> AbstractContextManager[None]:
        """Return a context manager that runs its body as one atomic transaction."""
