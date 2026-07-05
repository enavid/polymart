"""Unit tests for the payment gateway registry (the pluggable method->adapter seam)."""

from __future__ import annotations

import pytest

from src.application.payment.ports import (
    NextActionType,
    PaymentGateway,
    PaymentGatewayRegistry,
    PaymentIntent,
    PaymentStartResult,
)
from src.domain.payment.exceptions import UnsupportedPaymentMethodError
from src.domain.payment.value_objects import PaymentMethod


class _StubGateway(PaymentGateway):
    def __init__(self, method: PaymentMethod) -> None:
        self._method = method

    @property
    def method(self) -> PaymentMethod:
        return self._method

    def start(self, intent: PaymentIntent) -> PaymentStartResult:  # pragma: no cover - unused
        return PaymentStartResult(next_action=NextActionType.NONE)


class TestPaymentGatewayRegistry:
    def test_resolves_a_registered_method(self) -> None:
        gateway = _StubGateway(PaymentMethod.COD)
        registry = PaymentGatewayRegistry((gateway,))
        assert registry.for_method(PaymentMethod.COD) is gateway

    def test_raises_for_an_unregistered_method(self) -> None:
        registry = PaymentGatewayRegistry((_StubGateway(PaymentMethod.COD),))
        with pytest.raises(UnsupportedPaymentMethodError):
            registry.for_method(PaymentMethod.ONLINE)

    def test_rejects_a_duplicate_registration(self) -> None:
        with pytest.raises(ValueError):
            PaymentGatewayRegistry(
                (_StubGateway(PaymentMethod.COD), _StubGateway(PaymentMethod.COD))
            )
