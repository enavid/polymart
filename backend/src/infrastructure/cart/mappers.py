"""Mapping between the Cart domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.cart.entities import Cart, CartLine
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Sku
from src.infrastructure.cart.models import CartModel


def cart_to_domain(model: CartModel) -> Cart:
    """Rebuild the aggregate from a persisted cart row and its ordered line rows.

    Relies on the caller having loaded ``lines`` (ordered by position via the child
    model's ``Meta.ordering``). The owner is stringified so the domain owns a stable
    id independent of the database's integer key type.
    """
    return Cart(
        owner=str(model.owner_id),
        channel=ChannelRef(model.channel_slug),
        lines=[
            CartLine(sku=Sku(line.sku), quantity=CartQuantity(line.quantity))
            for line in model.lines.all()
        ],
        id=model.pk,
    )
