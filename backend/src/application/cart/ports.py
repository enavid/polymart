"""Ports (interfaces) for the cart use cases.

The application layer depends only on these abstractions. Concrete adapters (Django
ORM, catalog/channel bridges, in-memory fakes) live elsewhere and are injected at
the composition root, keeping the dependency rule pointing inward.

The pricing and channel readers are *narrow* boundaries onto neighbouring bounded
contexts: the cart learns a variant's current price and a channel's currency without
depending on the catalog or channel domains.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from src.domain.cart.entities import Cart
from src.domain.cart.value_objects import Money


class CartRepository(ABC):
    """Persistence boundary for the Cart aggregate.

    A cart is keyed by its owner and channel (one active cart per pair). ``get``
    never fails for a missing cart -- it returns an empty one -- so a first read and
    a first add behave the same.
    """

    @abstractmethod
    def get(self, owner: str, channel: str) -> Cart:
        """Return the owner's cart for this channel, or an empty cart if none exists.

        A read-only load (no lock). Mutations must go through ``apply`` so the whole
        read-modify-write is serialized.
        """

    @abstractmethod
    def apply(self, owner: str, channel: str, mutate: Callable[[Cart], None]) -> Cart:
        """Atomically load the owner's cart, apply ``mutate`` to it, and persist it.

        The load-mutate-persist runs as one unit under a row lock, so two concurrent
        mutations of the same cart cannot both read the same starting state and lose
        an update. ``mutate`` performs the domain operation (add/set/remove a line)
        on the loaded aggregate; if it raises a domain error (e.g.
        ``CartLineNotFoundError``) nothing is written and the error propagates.
        Returns the persisted cart.
        """

    @abstractmethod
    def merge_guest_into_user(self, guest_owner: str, user_owner: str) -> int:
        """Merge every guest cart into the same-channel user cart, then delete it.

        For each channel where the guest owns a cart, its lines are absorbed into the
        user's cart in that channel (quantities summed per variant, capped) and the
        guest cart is removed. Runs as one atomic unit so a merged guest cart is never
        left behind to be merged twice. Returns the number of channels merged;
        idempotent (a repeat finds no guest carts and merges nothing).
        """


class VariantPricingReader(ABC):
    """Narrow read boundary onto the catalog for cart pricing.

    The cart needs two facts about a variant without depending on the catalog
    domain: whether it exists, and its current price in a given channel (``None`` if
    it has no price there). The adapter bridges to the catalog context and returns a
    cart-domain ``Money``.
    """

    @abstractmethod
    def exists(self, sku: str) -> bool:
        """Return whether a catalog variant with this SKU exists."""

    @abstractmethod
    def price_of(self, sku: str, channel: str) -> Money | None:
        """Return the variant's current unit price in the channel, or ``None``."""


class ChannelReader(ABC):
    """Narrow read boundary onto the channel context for the cart.

    A cart is priced in one channel's currency; this exposes exactly that lookup
    without a dependency on the channel domain.
    """

    @abstractmethod
    def currency_of(self, channel: str) -> str | None:
        """Return the channel's ISO 4217 currency code, or ``None`` if it does not exist."""
