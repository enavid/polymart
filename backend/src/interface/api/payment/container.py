"""Composition root for the payment slice.

The only place that wires concrete infrastructure adapters into the payment use cases,
including the gateway registry -- the pluggable seam where a payment method's adapter is
registered. Cash on delivery is always registered; the online method is the offline mock
gateway in dev/test and the real Zarinpal adapter in production (chosen by settings, exactly
like the OTP dev SMS sender). Adding a method is registering an adapter here -- the domain
and use cases never change.

Views (and the capture Celery task) depend on these factories, never on infrastructure
directly.
"""

from __future__ import annotations

from django.conf import settings

from src.application.payment.ports import PaymentGateway, PaymentGatewayRegistry
from src.application.payment.use_cases import (
    CapturePayment,
    ConfirmCardToCardPayment,
    GetCardToCardInstructions,
    GetMyPayment,
    GetPaymentByGatewayReference,
    GetPaymentForOrder,
    InitiatePayment,
    PayWithWallet,
    RefundPayment,
    RejectCardToCardPayment,
    SubmitCardToCardReference,
)
from src.infrastructure.payment.card_to_card import SettingsCardToCardDirectory
from src.infrastructure.payment.clock import SystemClock
from src.infrastructure.payment.gateways import (
    CardToCardGateway,
    CashOnDeliveryGateway,
    MockOnlineGateway,
    ZarinpalGateway,
)
from src.infrastructure.payment.http import UrllibHttpTransport
from src.infrastructure.payment.reference_generator import SecurePaymentReferenceGenerator
from src.infrastructure.payment.repositories import (
    DjangoOrderReader,
    DjangoPaidOrders,
    DjangoPaymentRepository,
    DjangoUnitOfWork,
)
from src.infrastructure.payment.wallet_credit import WalletCreditAdapter
from src.infrastructure.payment.wallet_debit import WalletDebitAdapter
from src.interface.api.audit.container import build_audit_recorder
from src.interface.api.events.container import build_event_publisher
from src.interface.api.wallet.container import build_credit_wallet, build_debit_wallet

# Zarinpal endpoints, keyed by whether the sandbox is in use (production config).
_ZARINPAL_HOSTS = {
    True: "https://sandbox.zarinpal.com",
    False: "https://payment.zarinpal.com",
}


def _build_online_gateway() -> PaymentGateway:
    """The online-method adapter: the offline mock in dev/test, real Zarinpal in prod."""
    if settings.PAYMENT_ONLINE_MOCK:
        return MockOnlineGateway(mock_page_url=settings.PAYMENT_MOCK_GATEWAY_URL)
    host = _ZARINPAL_HOSTS[bool(settings.ZARINPAL_SANDBOX)]
    return ZarinpalGateway(
        transport=UrllibHttpTransport(),
        merchant_id=settings.ZARINPAL_MERCHANT_ID,
        callback_url=settings.PAYMENT_CALLBACK_URL,
        request_url=f"{host}/pg/v4/payment/request.json",
        verify_url=f"{host}/pg/v4/payment/verify.json",
        start_pay_url=f"{host}/pg/StartPay",
    )


def build_gateway_registry() -> PaymentGatewayRegistry:
    """The registered payment gateways (COD + card-to-card + the online method's adapter)."""
    return PaymentGatewayRegistry(
        (CashOnDeliveryGateway(), CardToCardGateway(), _build_online_gateway())
    )


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


def build_pay_with_wallet() -> PayWithWallet:
    return PayWithWallet(
        unit_of_work=DjangoUnitOfWork(),
        orders=DjangoOrderReader(),
        payments=DjangoPaymentRepository(),
        wallet_debit=WalletDebitAdapter(build_debit_wallet()),
        paid_orders=DjangoPaidOrders(),
        references=SecurePaymentReferenceGenerator(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
    )


def build_capture_payment() -> CapturePayment:
    return CapturePayment(
        unit_of_work=DjangoUnitOfWork(),
        payments=DjangoPaymentRepository(),
        gateways=build_gateway_registry(),
        paid_orders=DjangoPaidOrders(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
        clock=SystemClock(),
    )


def build_refund_payment() -> RefundPayment:
    return RefundPayment(
        unit_of_work=DjangoUnitOfWork(),
        payments=DjangoPaymentRepository(),
        wallet_credit=WalletCreditAdapter(build_credit_wallet()),
        audit=build_audit_recorder(),
    )


def build_get_payment_by_gateway_reference() -> GetPaymentByGatewayReference:
    return GetPaymentByGatewayReference(DjangoPaymentRepository())


def build_get_my_payment() -> GetMyPayment:
    return GetMyPayment(DjangoPaymentRepository())


def build_get_payment_for_order() -> GetPaymentForOrder:
    return GetPaymentForOrder(DjangoPaymentRepository())


def build_submit_card_to_card_reference() -> SubmitCardToCardReference:
    return SubmitCardToCardReference(
        unit_of_work=DjangoUnitOfWork(),
        payments=DjangoPaymentRepository(),
        audit=build_audit_recorder(),
    )


def build_confirm_card_to_card_payment() -> ConfirmCardToCardPayment:
    return ConfirmCardToCardPayment(
        unit_of_work=DjangoUnitOfWork(),
        payments=DjangoPaymentRepository(),
        paid_orders=DjangoPaidOrders(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
        clock=SystemClock(),
    )


def build_reject_card_to_card_payment() -> RejectCardToCardPayment:
    return RejectCardToCardPayment(
        unit_of_work=DjangoUnitOfWork(),
        payments=DjangoPaymentRepository(),
        audit=build_audit_recorder(),
    )


def build_get_card_to_card_instructions() -> GetCardToCardInstructions:
    return GetCardToCardInstructions(
        orders=DjangoOrderReader(),
        directory=SettingsCardToCardDirectory(),
    )
