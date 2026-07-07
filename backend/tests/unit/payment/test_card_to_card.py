"""Unit tests for the card-to-card use cases against fakes (no DB, no framework).

Card-to-card is a manual bank transfer the buyer makes and staff verify. These exercise the
four interactors: the buyer submitting their transfer reference (owner-scoped, once, only
while pending), staff confirming (capture + order paid + PaymentCaptured, idempotent) or
rejecting (fail, idempotent), and reading the per-channel destination card. The repositories,
directory, clock, and event bus are faked; the real adapters are wired at the composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.application.payment.ports import CardToCardDestination, CardToCardDirectory
from src.application.payment.use_cases import (
    ConfirmCardToCardPayment,
    ConfirmCardToCardPaymentCommand,
    GetCardToCardInstructions,
    RejectCardToCardPayment,
    RejectCardToCardPaymentCommand,
    SubmitCardToCardReference,
    SubmitCardToCardReferenceCommand,
)
from src.domain.payment.entities import Payment
from src.domain.payment.events import PaymentCaptured
from src.domain.payment.exceptions import (
    CardToCardNotConfiguredError,
    NotACardToCardPaymentError,
    PaymentNotAwaitingTransferError,
    PaymentNotConfirmableError,
    PaymentNotFoundError,
    PaymentOrderNotFoundError,
    TransferReferenceAlreadySubmittedError,
)
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)
from tests.unit.payment.test_use_cases import (
    FakeOrders,
    FakePaidOrders,
    FakePayments,
    FakeUnitOfWork,
    FixedClock,
    RecordingAudit,
    RecordingEventPublisher,
    _payable,
)

_OWNER = "u:7"
_ORDER_NUMBER = "ORD-XYZ789"
_REFERENCE = "PAY-CTC001"
_TRANSFER = "TRK-123456"


def _card_payment(
    *,
    status: PaymentStatus = PaymentStatus.PENDING,
    transfer_reference: str | None = None,
    owner: str = _OWNER,
    method: PaymentMethod = PaymentMethod.CARD_TO_CARD,
) -> Payment:
    return Payment(
        reference=PaymentReference(_REFERENCE),
        order_ref=OrderRef(_ORDER_NUMBER),
        owner=owner,
        method=method,
        amount=Money(amount=Decimal("150.00"), currency="IRR"),
        status=status,
        created_at=datetime(2026, 7, 6, tzinfo=UTC),
        transfer_reference=transfer_reference,
    )


def _payments_with(payment: Payment) -> FakePayments:
    payments = FakePayments()
    payments.add(payment)
    return payments


# --- SubmitCardToCardReference -------------------------------------------


class TestSubmitCardToCardReference:
    def _build(self, payments: FakePayments) -> tuple[SubmitCardToCardReference, RecordingAudit]:
        audit = RecordingAudit()
        return (
            SubmitCardToCardReference(
                unit_of_work=FakeUnitOfWork(), payments=payments, audit=audit
            ),
            audit,
        )

    def _command(self, transfer: str = _TRANSFER) -> SubmitCardToCardReferenceCommand:
        return SubmitCardToCardReferenceCommand(
            owner=_OWNER, order_number=_ORDER_NUMBER, transfer_reference=transfer
        )

    def test_records_the_transfer_reference_and_audits(self) -> None:
        payments = _payments_with(_card_payment())
        use_case, audit = self._build(payments)

        result = use_case.execute(self._command())

        assert result.transfer_reference == _TRANSFER
        assert payments.saved[0].transfer_reference == _TRANSFER
        entry = audit.records[-1]
        assert entry["action"] == "payment.transfer_submitted"
        fields = {c.field: c.after for c in entry["changes"]}  # type: ignore[attr-defined]
        assert fields["transfer_reference"] == _TRANSFER

    def test_trims_surrounding_whitespace(self) -> None:
        payments = _payments_with(_card_payment())
        use_case, _ = self._build(payments)

        result = use_case.execute(self._command(transfer="  TRK-9  "))

        assert result.transfer_reference == "TRK-9"

    def test_unknown_or_others_order_is_not_found(self) -> None:
        # No active payment for this owner's order (empty repo) -> indistinguishable 404.
        use_case, _ = self._build(FakePayments())
        with pytest.raises(PaymentNotFoundError):
            use_case.execute(self._command())

    def test_anothers_payment_is_unreachable(self) -> None:
        payments = _payments_with(_card_payment(owner="u:99"))
        use_case, _ = self._build(payments)
        with pytest.raises(PaymentNotFoundError):
            use_case.execute(self._command())

    def test_rejects_a_non_card_to_card_payment(self) -> None:
        payments = _payments_with(_card_payment(method=PaymentMethod.COD))
        use_case, _ = self._build(payments)
        with pytest.raises(NotACardToCardPaymentError):
            use_case.execute(self._command())

    def test_rejects_a_non_pending_payment(self) -> None:
        payments = _payments_with(_card_payment(status=PaymentStatus.CAPTURED))
        use_case, _ = self._build(payments)
        with pytest.raises(PaymentNotAwaitingTransferError):
            use_case.execute(self._command())

    def test_refuses_a_second_submission(self) -> None:
        payments = _payments_with(_card_payment(transfer_reference="TRK-FIRST"))
        use_case, _ = self._build(payments)
        with pytest.raises(TransferReferenceAlreadySubmittedError):
            use_case.execute(self._command())


# --- ConfirmCardToCardPayment --------------------------------------------


class TestConfirmCardToCardPayment:
    def _build(
        self, payments: FakePayments, paid: FakePaidOrders | None = None
    ) -> tuple[ConfirmCardToCardPayment, FakePaidOrders, RecordingAudit, RecordingEventPublisher]:
        paid = paid or FakePaidOrders()
        audit = RecordingAudit()
        events = RecordingEventPublisher()
        use_case = ConfirmCardToCardPayment(
            unit_of_work=FakeUnitOfWork(),
            payments=payments,
            paid_orders=paid,
            audit=audit,
            events=events,
            clock=FixedClock(),
        )
        return use_case, paid, audit, events

    def _command(self) -> ConfirmCardToCardPaymentCommand:
        return ConfirmCardToCardPaymentCommand(reference=_REFERENCE, actor="u:1")

    def test_captures_marks_paid_and_publishes(self) -> None:
        payments = _payments_with(_card_payment(transfer_reference=_TRANSFER))
        use_case, paid, audit, events = self._build(payments)

        result = use_case.execute(self._command())

        assert result.status is PaymentStatus.CAPTURED
        assert paid.paid == [_ORDER_NUMBER]
        [event] = events.events
        assert isinstance(event, PaymentCaptured)
        assert event.method == "card_to_card"
        assert event.amount == Decimal("150.00")
        entry = next(r for r in audit.records if r["action"] == "payment.captured")
        assert entry["actor"] == "u:1"
        fields = {c.field: c.after for c in entry["changes"]}  # type: ignore[attr-defined]
        assert fields["transfer_reference"] == _TRANSFER
        assert fields["method"] == "card_to_card"

    def test_is_idempotent_on_an_already_captured_payment(self) -> None:
        payments = _payments_with(
            _card_payment(status=PaymentStatus.CAPTURED, transfer_reference=_TRANSFER)
        )
        use_case, paid, _audit, events = self._build(payments)

        result = use_case.execute(self._command())

        assert result.status is PaymentStatus.CAPTURED
        assert paid.paid == []  # not re-paid
        assert events.events == []  # not re-announced

    def test_refuses_without_a_submitted_transfer_reference(self) -> None:
        payments = _payments_with(_card_payment(transfer_reference=None))
        use_case, paid, _audit, events = self._build(payments)
        with pytest.raises(PaymentNotConfirmableError):
            use_case.execute(self._command())
        assert paid.paid == []
        assert events.events == []

    def test_rejects_a_non_card_to_card_payment(self) -> None:
        payments = _payments_with(
            _card_payment(method=PaymentMethod.ONLINE, transfer_reference=_TRANSFER)
        )
        use_case, *_ = self._build(payments)
        with pytest.raises(NotACardToCardPaymentError):
            use_case.execute(self._command())

    def test_rejects_a_failed_payment(self) -> None:
        payments = _payments_with(_card_payment(status=PaymentStatus.FAILED))
        use_case, *_ = self._build(payments)
        with pytest.raises(PaymentNotConfirmableError):
            use_case.execute(self._command())

    def test_unknown_payment_is_not_found(self) -> None:
        use_case, *_ = self._build(FakePayments())
        with pytest.raises(PaymentNotFoundError):
            use_case.execute(self._command())


# --- RejectCardToCardPayment ---------------------------------------------


class TestRejectCardToCardPayment:
    def _build(self, payments: FakePayments) -> tuple[RejectCardToCardPayment, RecordingAudit]:
        audit = RecordingAudit()
        return (
            RejectCardToCardPayment(unit_of_work=FakeUnitOfWork(), payments=payments, audit=audit),
            audit,
        )

    def _command(self) -> RejectCardToCardPaymentCommand:
        return RejectCardToCardPaymentCommand(reference=_REFERENCE, actor="u:1")

    def test_fails_the_payment_and_audits(self) -> None:
        payments = _payments_with(_card_payment(transfer_reference=_TRANSFER))
        use_case, audit = self._build(payments)

        result = use_case.execute(self._command())

        assert result.status is PaymentStatus.FAILED
        entry = audit.records[-1]
        assert entry["action"] == "payment.rejected"
        assert entry["actor"] == "u:1"

    def test_is_idempotent_on_an_already_failed_payment(self) -> None:
        payments = _payments_with(_card_payment(status=PaymentStatus.FAILED))
        use_case, audit = self._build(payments)

        result = use_case.execute(self._command())

        assert result.status is PaymentStatus.FAILED
        assert not any(r["action"] == "payment.rejected" for r in audit.records)

    def test_cannot_reject_a_captured_payment(self) -> None:
        payments = _payments_with(_card_payment(status=PaymentStatus.CAPTURED))
        use_case, _ = self._build(payments)
        with pytest.raises(PaymentNotConfirmableError):
            use_case.execute(self._command())

    def test_rejects_a_non_card_to_card_payment(self) -> None:
        payments = _payments_with(_card_payment(method=PaymentMethod.COD))
        use_case, _ = self._build(payments)
        with pytest.raises(NotACardToCardPaymentError):
            use_case.execute(self._command())

    def test_unknown_payment_is_not_found(self) -> None:
        use_case, _ = self._build(FakePayments())
        with pytest.raises(PaymentNotFoundError):
            use_case.execute(self._command())


# --- GetCardToCardInstructions -------------------------------------------


class FakeDirectory(CardToCardDirectory):
    def __init__(self, cards: dict[str, CardToCardDestination] | None = None) -> None:
        self._cards = cards or {}

    def card_for(self, channel: str) -> CardToCardDestination | None:
        return self._cards.get(channel)


class TestGetCardToCardInstructions:
    _CARD = CardToCardDestination(card_number="6037-9911-1234-5678", card_holder="Store")

    def test_returns_the_channels_destination_card(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(channel="ir-main")})
        use_case = GetCardToCardInstructions(
            orders=orders, directory=FakeDirectory({"ir-main": self._CARD})
        )

        result = use_case.execute(owner=_OWNER, order_number=_ORDER_NUMBER)

        assert result == self._CARD

    def test_unknown_or_others_order_is_not_found(self) -> None:
        use_case = GetCardToCardInstructions(
            orders=FakeOrders({}), directory=FakeDirectory({"ir-main": self._CARD})
        )
        with pytest.raises(PaymentOrderNotFoundError):
            use_case.execute(owner=_OWNER, order_number=_ORDER_NUMBER)

    def test_an_unconfigured_channel_is_refused(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(channel="ir-main")})
        use_case = GetCardToCardInstructions(orders=orders, directory=FakeDirectory({}))
        with pytest.raises(CardToCardNotConfiguredError):
            use_case.execute(owner=_OWNER, order_number=_ORDER_NUMBER)
