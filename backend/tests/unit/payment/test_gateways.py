"""Unit tests for the online gateway adapters (Zarinpal against a fake transport; mock).

Zarinpal is exercised without a live network: a fake ``HttpTransport`` records the request
payloads and returns canned provider responses, so we verify the request/verify shapes and
the success/failure mapping (including the idempotent "already verified" code 101).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.application.payment.ports import NextActionType, PaymentIntent
from src.domain.payment.value_objects import Money, PaymentMethod, PaymentReference
from src.infrastructure.payment.gateways import (
    GatewayStartError,
    MockOnlineGateway,
    ZarinpalGateway,
)
from src.infrastructure.payment.http import HttpTransport


class FakeTransport(HttpTransport):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, payload))
        return self._responses.pop(0)


def _intent() -> PaymentIntent:
    return PaymentIntent(
        reference=PaymentReference("PAY-ABC123"),
        order_number="ORD-XYZ789",
        amount=Money(amount=Decimal("150000"), currency="IRR"),
        method=PaymentMethod.ONLINE,
    )


def _zarinpal(transport: HttpTransport) -> ZarinpalGateway:
    return ZarinpalGateway(
        transport=transport,
        merchant_id="MID-1",
        callback_url="https://shop/api/v1/payments/callback/",
        request_url="https://gw/request.json",
        verify_url="https://gw/verify.json",
        start_pay_url="https://gw/StartPay",
    )


class TestZarinpalStart:
    def test_requests_and_returns_a_redirect(self) -> None:
        transport = FakeTransport(
            [{"data": {"code": 100, "authority": "A0000000001"}, "errors": []}]
        )
        result = _zarinpal(transport).start(_intent())

        assert result.next_action is NextActionType.REDIRECT
        assert result.gateway_reference == "A0000000001"
        assert result.redirect_url == "https://gw/StartPay/A0000000001"
        # The request carries the merchant id, an integer amount, and the callback.
        url, payload = transport.calls[0]
        assert url == "https://gw/request.json"
        assert payload["merchant_id"] == "MID-1"
        assert payload["amount"] == 150000
        assert payload["callback_url"] == "https://shop/api/v1/payments/callback/"

    def test_a_rejected_request_raises(self) -> None:
        transport = FakeTransport([{"data": {"code": -9}, "errors": ["bad merchant"]}])
        with pytest.raises(GatewayStartError):
            _zarinpal(transport).start(_intent())


class TestZarinpalVerify:
    def test_a_successful_verify_captures(self) -> None:
        transport = FakeTransport([{"data": {"code": 100, "ref_id": 987654}, "errors": []}])
        verification = _zarinpal(transport).verify(
            gateway_reference="A1", amount=Money(amount=Decimal("150000"), currency="IRR")
        )
        assert verification.captured is True
        assert verification.provider_reference == "987654"
        _url, payload = transport.calls[0]
        assert payload == {"merchant_id": "MID-1", "amount": 150000, "authority": "A1"}

    def test_already_verified_is_still_captured(self) -> None:
        # Code 101 = already verified: idempotent at the provider, still "captured".
        transport = FakeTransport([{"data": {"code": 101, "ref_id": 987654}, "errors": []}])
        verification = _zarinpal(transport).verify(
            gateway_reference="A1", amount=Money(amount=Decimal("150000"), currency="IRR")
        )
        assert verification.captured is True

    def test_a_failed_verify_is_not_captured(self) -> None:
        transport = FakeTransport([{"data": {"code": -51}, "errors": ["failed"]}])
        verification = _zarinpal(transport).verify(
            gateway_reference="A1", amount=Money(amount=Decimal("150000"), currency="IRR")
        )
        assert verification.captured is False
        assert verification.provider_reference is None


class TestMockOnlineGateway:
    def test_start_redirects_to_the_mock_page_with_an_authority(self) -> None:
        gateway = MockOnlineGateway(mock_page_url="/api/v1/payments/mock-gateway/")
        result = gateway.start(_intent())
        assert result.next_action is NextActionType.REDIRECT
        assert result.gateway_reference == "MOCK-PAY-ABC123"
        assert result.redirect_url == "/api/v1/payments/mock-gateway/?authority=MOCK-PAY-ABC123"

    def test_verify_always_captures(self) -> None:
        gateway = MockOnlineGateway(mock_page_url="/x")
        verification = gateway.verify(
            gateway_reference="MOCK-1", amount=Money(amount=Decimal("1"), currency="IRR")
        )
        assert verification.captured is True
        assert verification.provider_reference == "MOCK-RID-MOCK-1"
