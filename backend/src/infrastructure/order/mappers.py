"""Mapping between the Order domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.order.entities import Order, OrderLine
from src.domain.order.value_objects import (
    CapturedShipping,
    CapturedTax,
    ChannelRef,
    Fulfillment,
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


def _captured_shipping_to_domain(model: OrderModel, currency: str) -> CapturedShipping | None:
    """Rebuild the captured shipping selection, or ``None`` if the order had no delivery charge.

    A blank ``shipping_method_code`` (the backfill default for orders that predate shipping, and
    the value manual/pre-invoice orders carry) means no shipping was captured -- the aggregate
    reads that as ``shipping=None`` and its total is the goods subtotal alone.
    """
    if not model.shipping_method_code:
        return None
    return CapturedShipping(
        method_code=model.shipping_method_code,
        method_name=model.shipping_method_name,
        cost=Money(amount=model.shipping_cost, currency=currency),
        is_pickup=model.shipping_is_pickup,
    )


def _captured_tax_to_domain(model: OrderModel, currency: str) -> CapturedTax | None:
    """Rebuild the captured tax, or ``None`` if the order was placed in an untaxed channel.

    A NULL ``tax_rate`` (the backfill value for orders that predate tax, and the value orders
    in an untaxed channel carry) means no tax was captured -- the aggregate reads that as
    ``tax=None`` and its total is the pre-tax amount. A stored rate of 0 is distinct: it
    rebuilds a captured 0-amount tax line.
    """
    if model.tax_rate is None:
        return None
    return CapturedTax(
        rate=model.tax_rate,
        amount=Money(amount=model.tax_amount, currency=currency),
    )


def _shipping_address_to_domain(model: OrderModel) -> ShippingAddress | None:
    """Rebuild the captured address, or ``None`` for a pickup order that captured none.

    A blank recipient name means no address was captured (a pickup/BOPIS order), mirroring
    how an empty shipping_method_code reads as no captured shipping.
    """
    if not model.shipping_recipient_name:
        return None
    return ShippingAddress(
        recipient_name=model.shipping_recipient_name,
        phone_number=model.shipping_phone_number,
        province=model.shipping_province,
        city=model.shipping_city,
        postal_code=model.shipping_postal_code,
        line1=model.shipping_line1,
        line2=model.shipping_line2 or None,
    )


def _fulfillment_to_domain(model: OrderModel) -> Fulfillment | None:
    """Rebuild the captured shipment (carrier + tracking), or ``None`` if not yet shipped.

    A blank ``fulfillment_carrier`` means no shipment was captured -- an unshipped order, or a
    pickup order (which never captures a shipment).
    """
    if not model.fulfillment_carrier:
        return None
    return Fulfillment(
        carrier=model.fulfillment_carrier,
        tracking_number=model.fulfillment_tracking_number,
        tracking_url=model.fulfillment_tracking_url or None,
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
        shipping=_captured_shipping_to_domain(model, currency),
        tax=_captured_tax_to_domain(model, currency),
        fulfillment=_fulfillment_to_domain(model),
        id=model.pk,
    )
