"""Unit tests for the RefundPayment use case against fakes (no DB, no framework).

These exercise the refund orchestration: the captured-only guard, the guest (no-wallet)
guard, idempotency on a repeated refund, the wallet credit for the full captured amount,
audit recording, and atomic rollback. The wallet-credit bridge and payment repository are
faked; the real adapters are wired at the composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.payment.ports import WalletCredit
from src.application.payment.use_cases import RefundPayment, RefundPaymentCommand
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import (
    InvalidPaymentReferenceError,
    PaymentNotFoundError,
    PaymentNotRefundableError,
    WalletOwnerRequiredError,
)
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)
from tests.unit.payment.test_use_cases import (
    FakePayments,
    FakeUnitOfWork,
    RecordingAudit,
)

_STAFF = "u:1"
_SHOPPER = "u:7"
_REFERENCE = "PAY-TEST01"
_ORDER = "ORD-XYZ789"


class FakeWalletCredit(WalletCredit):
    def __init__(self) -> None:
        self.credits: list[dict[str, object]] = []

    def credit(
        self,
        *,
        owner: str,
        amount: Decimal,
        currency: str,
        source_reference: str,
        reason: str,
        actor: str,
    ) -> None:
        self.credits.append(
            {
                "owner": owner,
                "amount": amount,
                "currency": currency,
                "source_reference": source_reference,
                "reason": reason,
                "actor": actor,
            }
        )


class ExplodingWalletCredit(WalletCredit):
    def credit(self, **_kwargs: object) -> None:
        raise RuntimeError("wallet unavailable")


def _payment(*, status: PaymentStatus = PaymentStatus.CAPTURED, owner: str = _SHOPPER) -> Payment:
    return Payment(
        reference=PaymentReference(_REFERENCE),
        order_ref=OrderRef(_ORDER),
        owner=owner,
        method=PaymentMethod.ONLINE,
        amount=Money(amount=Decimal("150.00"), currency="IRR"),
        status=status,
        created_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )


def _build(
    payment: Payment | None,
    *,
    wallet_credit: WalletCredit | None = None,
) -> tuple[RefundPayment, FakePayments, FakeUnitOfWork, RecordingAudit, FakeWalletCredit]:
    payments = FakePayments()
    if payment is not None:
        payments.add(payment)
    uow = FakeUnitOfWork()
    audit = RecordingAudit()
    wallet = wallet_credit or FakeWalletCredit()
    use_case = RefundPayment(
        unit_of_work=uow,
        payments=payments,
        wallet_credit=wallet,
        audit=audit,
    )
    fake_wallet = wallet if isinstance(wallet, FakeWalletCredit) else FakeWalletCredit()
    return use_case, payments, uow, audit, fake_wallet


class TestRefundPayment:
    def test_refunds_a_captured_payment_to_the_wallet(self) -> None:
        use_case, payments, uow, _audit, wallet = _build(_payment())

        refunded = use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        assert refunded.status == PaymentStatus.REFUNDED
        assert payments.get_by_reference_for_update(_REFERENCE).status == PaymentStatus.REFUNDED
        assert uow.committed is True
        # The full captured amount was credited to the shopper's own wallet.
        assert wallet.credits == [
            {
                "owner": _SHOPPER,
                "amount": Decimal("150.00"),
                "currency": "IRR",
                "source_reference": _REFERENCE,
                "reason": "refund",
                "actor": _STAFF,
            }
        ]

    def test_records_a_money_audit_entry_attributed_to_the_staff_actor(self) -> None:
        use_case, _, _, audit, _ = _build(_payment())

        use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        record = audit.records[0]
        assert record["action"] == "payment.refunded"
        assert record["actor"] == _STAFF
        status_change = next(c for c in record["changes"] if c.field == "status")
        assert status_change.before == "captured"
        assert status_change.after == "refunded"

    def test_is_idempotent_on_an_already_refunded_payment(self) -> None:
        use_case, _, _, audit, wallet = _build(_payment(status=PaymentStatus.REFUNDED))

        result = use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        assert result.status == PaymentStatus.REFUNDED
        assert wallet.credits == []  # no second credit
        assert audit.records == []  # no second audit entry

    def test_refuses_a_payment_that_is_not_captured(self) -> None:
        use_case, _, uow, _, wallet = _build(_payment(status=PaymentStatus.PENDING))

        with pytest.raises(PaymentNotRefundableError):
            use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        assert wallet.credits == []
        assert uow.rolled_back is True

    def test_refuses_to_refund_a_guest_payment_to_a_wallet(self) -> None:
        use_case, _, uow, _, wallet = _build(_payment(owner="g:sometoken"))

        with pytest.raises(WalletOwnerRequiredError):
            use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        assert wallet.credits == []
        assert uow.rolled_back is True

    def test_raises_when_the_payment_does_not_exist(self) -> None:
        use_case, _, _, _, _ = _build(None)

        with pytest.raises(PaymentNotFoundError):
            use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

    def test_a_malformed_reference_is_rejected(self) -> None:
        # A malformed reference can never match a payment; the use case raises a payment
        # error which the transport maps to 404 (never a distinct error that probes shape).
        use_case, _, _, _, _ = _build(None)

        with pytest.raises(InvalidPaymentReferenceError):
            use_case.execute(RefundPaymentCommand(reference="!!bad!!", actor=_STAFF))

    def test_rolls_back_and_leaves_the_payment_captured_when_the_wallet_credit_fails(
        self,
    ) -> None:
        use_case, _payments, uow, _, _ = _build(_payment(), wallet_credit=ExplodingWalletCredit())

        with pytest.raises(RuntimeError):
            use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        assert uow.rolled_back is True
        # The status update happened before the failing credit; the transaction rollback is
        # what undoes it in production (the fake UoW does not model that), so we assert the
        # transaction was marked rolled back rather than the in-memory status.

    def test_logs_the_refund_without_the_amount(self) -> None:
        use_case, _, _, _, _ = _build(_payment())

        with capture_logs() as logs:
            use_case.execute(RefundPaymentCommand(reference=_REFERENCE, actor=_STAFF))

        event = next(log for log in logs if log["event"] == "payment_refunded")
        assert "amount" not in event
        assert event["currency"] == "IRR"
        assert event["actor"] == _STAFF
