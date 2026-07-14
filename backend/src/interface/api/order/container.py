"""Composition root for the order slice.

The only place that wires concrete infrastructure adapters into the order use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.order.use_cases import (
    CancelMyOrder,
    ConfirmOrderPickup,
    CreateManualOrder,
    GetMyOrder,
    GetOrderForInvoice,
    ListMyOrders,
    MarkOrderReadyForPickup,
    PlaceOrder,
    ShipOrder,
)
from src.infrastructure.order.clock import SystemClock
from src.infrastructure.order.number_generator import SecureOrderNumberGenerator
from src.infrastructure.order.repositories import (
    ConfiguredShippingRateReader,
    ConfiguredTaxCalculator,
    DjangoAddressReader,
    DjangoCartForCheckout,
    DjangoChannelReader,
    DjangoInventory,
    DjangoOrderRepository,
    DjangoPricingReader,
    DjangoProductTaxClassReader,
    DjangoUnitOfWork,
    DjangoVariantWeightReader,
)
from src.interface.api.audit.container import build_audit_recorder
from src.interface.api.events.container import build_event_publisher


def build_place_order() -> PlaceOrder:
    return PlaceOrder(
        unit_of_work=DjangoUnitOfWork(),
        carts=DjangoCartForCheckout(),
        pricing=DjangoPricingReader(),
        weights=DjangoVariantWeightReader(),
        channels=DjangoChannelReader(),
        addresses=DjangoAddressReader(),
        shipping=ConfiguredShippingRateReader(),
        tax=ConfiguredTaxCalculator(),
        tax_classes=DjangoProductTaxClassReader(),
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
        tax=ConfiguredTaxCalculator(),
        tax_classes=DjangoProductTaxClassReader(),
        inventory=DjangoInventory(),
        orders=DjangoOrderRepository(),
        numbers=SecureOrderNumberGenerator(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
    )


def build_get_order_for_invoice() -> GetOrderForInvoice:
    return GetOrderForInvoice(DjangoOrderRepository())


def build_ship_order() -> ShipOrder:
    return ShipOrder(
        unit_of_work=DjangoUnitOfWork(),
        orders=DjangoOrderRepository(),
        audit=build_audit_recorder(),
    )


def build_mark_order_ready_for_pickup() -> MarkOrderReadyForPickup:
    return MarkOrderReadyForPickup(
        unit_of_work=DjangoUnitOfWork(),
        orders=DjangoOrderRepository(),
        audit=build_audit_recorder(),
    )


def build_confirm_order_pickup() -> ConfirmOrderPickup:
    return ConfirmOrderPickup(
        unit_of_work=DjangoUnitOfWork(),
        orders=DjangoOrderRepository(),
        audit=build_audit_recorder(),
    )
