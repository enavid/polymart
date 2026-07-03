"""The Cart aggregate: a shopper's persistent list of intended purchases.

A cart belongs to one owner and is priced in one channel. It holds an ordered set
of lines, each a variant reference and a quantity; a variant appears at most once
(adding it again increases its quantity). Pricing is deliberately *not* here: the
current price of a variant lives in the catalog and is resolved at read time by a
domain service, so the aggregate stays a pure structure with no I/O.

No Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.cart.exceptions import CartLineNotFoundError, DuplicateCartLineError
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Sku


@dataclass
class CartLine:
    """One variant in a cart, with the quantity intended for purchase."""

    sku: Sku
    quantity: CartQuantity


@dataclass
class Cart:
    """A shopper's cart for one channel.

    Identity is the database ``id`` once persisted; the owner/channel pair is the
    stable business key (one active cart per owner per channel). The owner is the
    caller's stable user id -- the cart is always resolved from the authenticated
    user, never from a client-supplied id, so one shopper can never reach another's.
    """

    owner: str
    channel: ChannelRef
    lines: list[CartLine] = field(default_factory=list)
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        # Rebuilt-from-storage carts must satisfy the same invariant as mutated ones:
        # a variant appears at most once.
        seen: set[str] = set()
        for line in self.lines:
            if line.sku.value in seen:
                raise DuplicateCartLineError(line.sku.value)
            seen.add(line.sku.value)

    def _find(self, sku: Sku) -> CartLine | None:
        for line in self.lines:
            if line.sku.value == sku.value:
                return line
        return None

    def add_item(self, sku: Sku, quantity: CartQuantity) -> None:
        """Add ``quantity`` of ``sku``; if the line already exists, increase it.

        The summed quantity is re-validated, so pushing a line over the maximum
        fails rather than silently capping.
        """
        existing = self._find(sku)
        if existing is None:
            self.lines.append(CartLine(sku=sku, quantity=quantity))
        else:
            existing.quantity = existing.quantity.plus(quantity)

    def set_item(self, sku: Sku, quantity: CartQuantity) -> None:
        """Replace the quantity of an existing line (never creates one)."""
        existing = self._find(sku)
        if existing is None:
            raise CartLineNotFoundError(sku.value)
        existing.quantity = quantity

    def remove_item(self, sku: Sku) -> None:
        """Remove an existing line (raises if the cart does not contain it)."""
        existing = self._find(sku)
        if existing is None:
            raise CartLineNotFoundError(sku.value)
        self.lines.remove(existing)

    def merge_from(self, other: Cart) -> None:
        """Absorb another cart's lines into this one (guest -> user on login).

        A variant present in both carts has its quantities summed (capped, so an
        absurd combined total cannot make a login fail); a variant only in ``other``
        is appended. This cart's existing lines keep their order; newly seen variants
        follow. Purely structural: no pricing, no I/O.
        """
        for line in other.lines:
            existing = self._find(line.sku)
            if existing is None:
                self.lines.append(CartLine(sku=line.sku, quantity=line.quantity))
            else:
                existing.quantity = existing.quantity.capped_sum(line.quantity)
