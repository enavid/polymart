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

    def test_capture_and_fail_helpers(self) -> None:
        assert _payment(PaymentStatus.PENDING).capture().status is PaymentStatus.CAPTURED
        assert _payment(PaymentStatus.PENDING).fail().status is PaymentStatus.FAILED
        assert _payment(PaymentStatus.AUTHORIZED).capture().status is PaymentStatus.CAPTURED

    def test_capture_from_a_terminal_state_is_illegal(self) -> None:
        with pytest.raises(IllegalPaymentTransitionError):
            _payment(PaymentStatus.FAILED).capture()


class TestGatewayReference:
    def test_defaults_to_none(self) -> None:
        assert _payment().gateway_reference is None

    def test_sets_the_reference_once(self) -> None:
        payment = _payment().with_gateway_reference("A0000000000001")
        assert payment.gateway_reference == "A0000000000001"

    def test_refuses_to_overwrite(self) -> None:
        payment = _payment().with_gateway_reference("A1")
        with pytest.raises(ValueError):
            payment.with_gateway_reference("A2")

    def test_transition_carries_the_reference(self) -> None:
        captured = _payment().with_gateway_reference("A1").capture()
        assert captured.gateway_reference == "A1"
        assert captured.status is PaymentStatus.CAPTURED


class TestTransferReference:
    def test_defaults_to_none(self) -> None:
        assert _payment().transfer_reference is None

    def test_sets_the_transfer_reference_once(self) -> None:
        payment = _payment().with_transfer_reference("TRK-123456")
        assert payment.transfer_reference == "TRK-123456"

    def test_refuses_to_overwrite(self) -> None:
        payment = _payment().with_transfer_reference("TRK-1")
        with pytest.raises(ValueError):
            payment.with_transfer_reference("TRK-2")

    def test_transition_carries_the_transfer_reference(self) -> None:
        captured = _payment().with_transfer_reference("TRK-1").capture()
        assert captured.transfer_reference == "TRK-1"
        assert captured.status is PaymentStatus.CAPTURED
