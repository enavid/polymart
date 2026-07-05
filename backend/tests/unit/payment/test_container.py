"""The payment composition root picks the right online adapter per settings."""

from __future__ import annotations

from django.test import override_settings

from src.domain.payment.value_objects import PaymentMethod
from src.infrastructure.payment.gateways import MockOnlineGateway, ZarinpalGateway
from src.interface.api.payment.container import build_gateway_registry


@override_settings(PAYMENT_ONLINE_MOCK=True)
def test_dev_wires_the_mock_online_gateway() -> None:
    gateway = build_gateway_registry().for_method(PaymentMethod.ONLINE)
    assert isinstance(gateway, MockOnlineGateway)


@override_settings(PAYMENT_ONLINE_MOCK=False, ZARINPAL_MERCHANT_ID="MID", ZARINPAL_SANDBOX=True)
def test_prod_wires_the_real_zarinpal_gateway() -> None:
    gateway = build_gateway_registry().for_method(PaymentMethod.ONLINE)
    assert isinstance(gateway, ZarinpalGateway)
