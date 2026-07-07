"""Composition root for the order slice.

The only place that wires concrete infrastructure adapters into the order use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.order.use_cases import (
    CancelMyOrder,
    CreateManualOrder,
    GetMyOrder,
    GetOrderForInvoice,
    ListMyOrders,
    PlaceOrder,
)
from src.infrastructure.order.clock import SystemClock
from src.infrastructure.order.number_generator import SecureOrderNumberGenerator
from src.infrastructure.order.repositories import (
    DjangoAddressReader,
    DjangoCartForCheckout,
    DjangoChannelReader,
    DjangoInventory,
    DjangoOrderRepository,
    DjangoPricingReader,
    DjangoUnitOfWork,
)
from src.interface.api.audit.container import build_audit_recorder
from src.interface.api.events.container import build_event_publisher


def build_place_order() -> PlaceOrder:
    return PlaceOrder(
        unit_of_work=DjangoUnitOfWork(),
        carts=DjangoCartForCheckout(),
        pricing=DjangoPricingReader(),
        channels=DjangoChannelReader(),
        addresses=DjangoAddressReader(),
        inventory=DjangoInventory(),
        orders=DjangoOrderRepository(),
        numbers=SecureOrderNumberGenerator(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
    )


def build_list_my_orders() -> ListMyOrders:
    return ListMyOrders(DjangoOrderRepository())


def build_get_my_order() -> GetMyOrder:
    return GetMyOrder(DjangoOrderRepository())


def build_cancel_my_order() -> CancelMyOrder:
    return CancelMyOrder(
        unit_of_work=DjangoUnitOfWork(),
        orders=DjangoOrderRepository(),
        inventory=DjangoInventory(),
        audit=build_audit_recorder(),
    )


def build_create_manual_order() -> CreateManualOrder:
    return CreateManualOrder(
        unit_of_work=DjangoUnitOfWork(),
        pricing=DjangoPricingReader(),
        channels=DjangoChannelReader(),
        inventory=DjangoInventory(),
        orders=DjangoOrderRepository(),
        numbers=SecureOrderNumberGenerator(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
    )


def build_get_order_for_invoice() -> GetOrderForInvoice:
    return GetOrderForInvoice(DjangoOrderRepository())
