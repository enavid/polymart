"""Unit tests for the Payment aggregate and its state machine (pure, no DB)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import IllegalPaymentTransitionError
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)


def _payment(status: PaymentStatus = PaymentStatus.PENDING) -> Payment:
    return Payment(
        reference=PaymentReference("PAY-ABC123"),
        order_ref=OrderRef("ORD-XYZ789"),
        owner="u:1",
        method=PaymentMethod.COD,
        amount=Money(amount=Decimal("100.00"), currency="IRR"),
        status=status,
        created_at=datetime(2026, 7, 5, tzinfo=UTC),
    )


class TestConstruction:
    def test_holds_its_fields(self) -> None:
        payment = _payment()
        assert payment.reference.value == "PAY-ABC123"
        assert payment.order_ref.value == "ORD-XYZ789"
        assert payment.owner == "u:1"
        assert payment.method is PaymentMethod.COD
        assert payment.amount.amount == Decimal("100.00")
        assert payment.status is PaymentStatus.PENDING
        assert payment.id is None

    def test_is_frozen(self) -> None:
        payment = _payment()
        with pytest.raises(FrozenInstanceError):
            payment.status = PaymentStatus.CAPTURED  # type: ignore[misc]


class TestStateMachine:
    @pytest.mark.parametrize(
        ("start", "target"),
        [
            (PaymentStatus.PENDING, PaymentStatus.AUTHORIZED),
            (PaymentStatus.PENDING, PaymentStatus.CAPTURED),
            (PaymentStatus.PENDING, PaymentStatus.FAILED),
            (PaymentStatus.PENDING, PaymentStatus.CANCELLED),
            (PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED),
            (PaymentStatus.AUTHORIZED, PaymentStatus.VOIDED),
            (PaymentStatus.AUTHORIZED, PaymentStatus.FAILED),
            (PaymentStatus.CAPTURED, PaymentStatus.REFUNDED),
        ],
    )
    def test_allows_legal_transitions(self, start: PaymentStatus, target: PaymentStatus) -> None:
        moved = _payment(start).transition_to(target)
        assert moved.status is target

    def test_transition_returns_a_new_instance(self) -> None:
        original = _payment(PaymentStatus.PENDING)
        moved = original.transition_to(PaymentStatus.CAPTURED)
        assert moved is not original
        assert original.status is PaymentStatus.PENDING  # unchanged
        # Everything else is carried over.
        assert moved.reference == original.reference
        assert moved.amount == original.amount

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            (PaymentStatus.PENDING, PaymentStatus.REFUNDED),  # can't refund an uncaptured
            (PaymentStatus.PENDING, PaymentStatus.VOIDED),  # nothing to void yet
            (PaymentStatus.CAPTURED, PaymentStatus.CANCELLED),  # captured -> refund only
            (PaymentStatus.CAPTURED, PaymentStatus.FAILED),
            (PaymentStatus.FAILED, PaymentStatus.CAPTURED),  # terminal
            (PaymentStatus.CANCELLED, PaymentStatus.PENDING),  # terminal
            (PaymentStatus.VOIDED, PaymentStatus.CAPTURED),  # terminal
            (PaymentStatus.REFUNDED, PaymentStatus.CAPTURED),  # terminal
        ],
    )
    def test_rejects_illegal_transitions(self, start: PaymentStatus, target: PaymentStatus) -> None:
        with pytest.raises(IllegalPaymentTransitionError):
            _payment(start).transition_to(target)

    def test_illegal_transition_carries_states(self) -> None:
        with pytest.raises(IllegalPaymentTransitionError) as exc:
            _payment(PaymentStatus.FAILED).transition_to(PaymentStatus.CAPTURED)
        assert exc.value.current == "failed"
        assert exc.value.target == "captured"
