"""Composition root for the payment slice.

The only place that wires concrete infrastructure adapters into the payment use cases,
including the gateway registry -- the pluggable seam where a payment method's adapter is
registered. This slice registers cash on delivery; a later slice adds the online gateway
here without touching the domain or the use case.

Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.payment.ports import PaymentGatewayRegistry
from src.application.payment.use_cases import (
    GetMyPayment,
    GetPaymentForOrder,
    InitiatePayment,
)
from src.infrastructure.payment.clock import SystemClock
from src.infrastructure.payment.gateways import CashOnDeliveryGateway
from src.infrastructure.payment.reference_generator import SecurePaymentReferenceGenerator
from src.infrastructure.payment.repositories import (
    DjangoOrderReader,
    DjangoPaymentRepository,
    DjangoUnitOfWork,
)
from src.interface.api.audit.container import build_audit_recorder


def build_gateway_registry() -> PaymentGatewayRegistry:
    """The registered payment gateways. Add new method adapters (online, ...) here."""
    return PaymentGatewayRegistry((CashOnDeliveryGateway(),))


def build_initiate_payment() -> InitiatePayment:
    return InitiatePayment(
        unit_of_work=DjangoUnitOfWork(),
        orders=DjangoOrderReader(),
        payments=DjangoPaymentRepository(),
        gateways=build_gateway_registry(),
        references=SecurePaymentReferenceGenerator(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    )


def build_get_my_payment() -> GetMyPayment:
    return GetMyPayment(DjangoPaymentRepository())


def build_get_payment_for_order() -> GetPaymentForOrder:
    return GetPaymentForOrder(DjangoPaymentRepository())
