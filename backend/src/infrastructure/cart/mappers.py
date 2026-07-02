"""Mapping between the Cart domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.cart.entities import Cart, CartLine
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Sku
from src.infrastructure.cart.models import CartModel


def _owner_id(model: CartModel) -> str:
    """Encode a persisted cart row's owner as the application's prefixed id.

    ``u:<pk>`` for a user cart, ``g:<token>`` for a guest cart. Mirrors the encoding
    produced at the HTTP boundary (see ``src.interface.api.guest``) so an id read back
    here keys the same row on the next request.
    """
    if model.owner_id is not None:
        return f"u:{model.owner_id}"
    return f"g:{model.guest_token}"


def cart_to_domain(model: CartModel) -> Cart:
    """Rebuild the aggregate from a persisted cart row and its ordered line rows.

    Relies on the caller having loaded ``lines`` (ordered by position via the child
    model's ``Meta.ordering``). The owner is rebuilt as the prefixed, stable string id
    the application layer keys carts by (``u:<pk>`` for a user, ``g:<token>`` for a
    guest), independent of the database's key types.
    """
    return Cart(
        owner=_owner_id(model),
        channel=ChannelRef(model.channel_slug),
        lines=[
            CartLine(sku=Sku(line.sku), quantity=CartQuantity(line.quantity))
            for line in model.lines.all()
        ],
        id=model.pk,
    )
