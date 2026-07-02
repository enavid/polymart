"""Mapping between the Order domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.order.entities import Order, OrderLine
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    Sku,
)
from src.infrastructure.order.models import OrderLineModel, OrderModel


def _line_to_domain(model: OrderLineModel, currency: str) -> OrderLine:
    return OrderLine(
        sku=Sku(model.sku),
        quantity=OrderQuantity(model.quantity),
        unit_price=Money(amount=model.unit_price, currency=currency),
        line_total=Money(amount=model.line_total, currency=currency),
    )


def order_to_domain(model: OrderModel) -> Order:
    """Rebuild the aggregate from a persisted order row and its ordered line rows.

    Relies on the caller having loaded ``lines`` (ordered by position via the child
    model's ``Meta.ordering``). The owner is stringified so the domain owns a stable id
    independent of the database's integer key type.
    """
    currency = model.currency_code
    return Order(
        number=OrderNumber(model.number),
        owner=str(model.owner_id),
        channel=ChannelRef(model.channel_slug),
        currency=currency,
        lines=tuple(_line_to_domain(line, currency) for line in model.lines.all()),
        total=Money(amount=model.total, currency=currency),
        status=OrderStatus(model.status),
        placed_at=model.placed_at,
        id=model.pk,
    )
