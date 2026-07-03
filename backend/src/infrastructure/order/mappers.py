"""Mapping between the Order domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.order.entities import Order, OrderLine
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    ShippingAddress,
    Sku,
)
from src.infrastructure.order.models import OrderLineModel, OrderModel


def _owner_id(model: OrderModel) -> str:
    """Rebuild the application's opaque, prefixed owner id from the order's columns.

    ``u:<pk>`` for a user order, ``g:<token>`` for a guest order -- the same encoding the
    cart uses and the HTTP boundary produces, so the domain owns one stable string id
    regardless of which column stores it.
    """
    if model.owner_id is not None:
        return f"u:{model.owner_id}"
    return f"g:{model.guest_token}"


def _line_to_domain(model: OrderLineModel, currency: str) -> OrderLine:
    return OrderLine(
        sku=Sku(model.sku),
        quantity=OrderQuantity(model.quantity),
        unit_price=Money(amount=model.unit_price, currency=currency),
        line_total=Money(amount=model.line_total, currency=currency),
    )


def _shipping_address_to_domain(model: OrderModel) -> ShippingAddress:
    return ShippingAddress(
        recipient_name=model.shipping_recipient_name,
        phone_number=model.shipping_phone_number,
        province=model.shipping_province,
        city=model.shipping_city,
        postal_code=model.shipping_postal_code,
        line1=model.shipping_line1,
        line2=model.shipping_line2 or None,
    )


def order_to_domain(model: OrderModel) -> Order:
    """Rebuild the aggregate from a persisted order row and its ordered line rows.

    Relies on the caller having loaded ``lines`` (ordered by position via the child
    model's ``Meta.ordering``). The owner is rebuilt as the opaque ``u:``/``g:`` id so the
    domain owns one stable string id independent of which column stores it.
    """
    currency = model.currency_code
    return Order(
        number=OrderNumber(model.number),
        owner=_owner_id(model),
        channel=ChannelRef(model.channel_slug),
        currency=currency,
        lines=tuple(_line_to_domain(line, currency) for line in model.lines.all()),
        total=Money(amount=model.total, currency=currency),
        status=OrderStatus(model.status),
        placed_at=model.placed_at,
        shipping_address=_shipping_address_to_domain(model),
        id=model.pk,
    )
