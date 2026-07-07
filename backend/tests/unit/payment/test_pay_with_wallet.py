"""Unit tests for the PayWithWallet use case against fakes (no DB, no framework).

These exercise the pay-with-wallet orchestration: the signed-in-user guard (a guest has no
wallet), the order-payability checks (owner-scoping, status, the double-initiation guard),
the amount captured from the order total (never client-supplied), the wallet debit for the
full amount, the immediate capture + order-paid marking, audit recording, and atomic
rollback on an uncovered balance. The wallet-debit bridge and repositories are faked; the
real adapters are wired at the composition root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.payment.ports import WalletDebit
from src.application.payment.use_cases import PayWithWallet, PayWithWalletCommand
from src.application.shared.owner import safe_owner
from src.domain.payment.entities import Payment
from src.domain.payment.events import PaymentCaptured
from src.domain.payment.exceptions import (
    InsufficientWalletBalanceError,
    OrderNotPayableError,
    PaymentAlreadyExistsError,
    PaymentOrderNotFoundError,
    WalletPaymentRequiresUserError,
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
    FixedReferences,
    RecordingAudit,
    RecordingEventPublisher,
    _payable,
)

_OWNER = "u:7"
_ORDER_NUMBER = "ORD-XYZ789"


class FakeWalletDebit(WalletDebit):
    """Records debits; optionally refuses (insufficient balance) like the real adapter."""

    def __init__(self, *, sufficient: bool = True) -> None:
        self._sufficient = sufficient
        self.debits: list[dict[str, object]] = []

    def debit(
        self,
        *,
        owner: str,
        amount: Decimal,
        currency: str,
        source_reference: str,
        reason: str,
        actor: str,
    ) -> None:
        if not self._sufficient:
            raise InsufficientWalletBalanceError(source_reference)
        self.debits.append(
            {
                "owner": owner,
                "amount": amount,
                "currency": currency,
                "source_reference": source_reference,
                "reason": reason,
                "actor": actor,
            }
        )


def _build(
    *,
    orders: FakeOrders,
    payments: FakePayments | None = None,
    wallet_debit: FakeWalletDebit | None = None,
    uow: FakeUnitOfWork | None = None,
    paid: FakePaidOrders | None = None,
    audit: RecordingAudit | None = None,
    events: RecordingEventPublisher | None = None,
) -> tuple[
    PayWithWallet,
    FakeUnitOfWork,
    FakePayments,
    FakePaidOrders,
    RecordingAudit,
    FakeWalletDebit,
    RecordingEventPublisher,
]:
    uow = uow or FakeUnitOfWork()
    payments = payments if payments is not None else FakePayments()
    paid = paid or FakePaidOrders()
    audit = audit or RecordingAudit()
    events = events or RecordingEventPublisher()
    wallet_debit = wallet_debit or FakeWalletDebit()
    use_case = PayWithWallet(
        unit_of_work=uow,
        orders=orders,
        payments=payments,
        wallet_debit=wallet_debit,
        paid_orders=paid,
        references=FixedReferences(),
        clock=FixedClock(),
        audit=audit,
        events=events,
    )
    return use_case, uow, payments, paid, audit, wallet_debit, events


class TestPayWithWalletSuccess:
    def test_debits_the_wallet_captures_the_payment_and_marks_the_order_paid(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="150.00")})
        use_case, uow, _payments, paid, _, wallet, events = _build(orders=orders)

        result = use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))

        assert uow.committed is True
        assert result.payment.status is PaymentStatus.CAPTURED
        assert result.payment.method is PaymentMethod.WALLET
        assert result.next_action.value == "none"
        assert result.redirect_url is None
        # The order was paid in the same transaction.
        assert paid.paid == [_ORDER_NUMBER]
        # The instant capture announces PaymentCaptured on the event bus, like any capture.
        [event] = events.events
        assert isinstance(event, PaymentCaptured)
        assert event.method == "wallet"
        assert event.amount == Decimal("150.00")
        assert event.order_number == _ORDER_NUMBER
        # The full order total was debited from the payer's own wallet, keyed on the payment.
        assert wallet.debits == [
            {
                "owner": _OWNER,
                "amount": Decimal("150.00"),
                "currency": "IRR",
                "source_reference": "PAY-TEST01",
                "reason": "order_payment",
                "actor": _OWNER,
            }
        ]

    def test_captures_the_amount_from_the_order_total_not_the_client(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="42.00")})
        use_case, *_rest, wallet, _events = _build(orders=orders)

        result = use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))

        assert result.payment.amount == Money(amount=Decimal("42.00"), currency="IRR")
        assert wallet.debits[0]["amount"] == Decimal("42.00")

    def test_audits_the_initiation_and_the_capture(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="99.00")})
        use_case, _, _, _, audit, _, _events = _build(orders=orders)

        use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))

        actions = [r["action"] for r in audit.records]
        assert "payment.initiated" in actions
        assert "payment.captured" in actions
        captured = next(r for r in audit.records if r["action"] == "payment.captured")
        assert captured["actor"] == safe_owner(_OWNER)
        fields = {c.field: c.after for c in captured["changes"]}  # type: ignore[attr-defined]
        assert fields["status"] == "captured"
        assert fields["amount"] == "99.00"

    def test_logs_without_the_amount(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="99.00")})
        use_case, *_ = _build(orders=orders)

        with capture_logs() as logs:
            use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))

        assert not any("99.00" in str(event) for event in logs)


class TestPayWithWalletFailures:
    def test_refuses_a_guest_before_opening_the_transaction(self) -> None:
        orders = FakeOrders({("g:tok", _ORDER_NUMBER): _payable()})
        use_case, uow, payments, paid, _, wallet, _events = _build(orders=orders)

        with pytest.raises(WalletPaymentRequiresUserError):
            use_case.execute(PayWithWalletCommand(owner="g:tok", order_number=_ORDER_NUMBER))

        assert payments.saved == []
        assert wallet.debits == []
        assert paid.paid == []
        assert uow.committed is False

    def test_refuses_when_the_balance_cannot_cover_the_order(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="150.00")})
        use_case, uow, _payments, paid, audit, _, events = _build(
            orders=orders, wallet_debit=FakeWalletDebit(sufficient=False)
        )

        with pytest.raises(InsufficientWalletBalanceError):
            use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))

        # Nothing settled: the order is not paid, no capture announced, the txn rolled back.
        assert paid.paid == []
        assert not any(r["action"] == "payment.captured" for r in audit.records)
        assert events.events == []
        assert uow.rolled_back is True

    def test_rejects_an_unknown_order(self) -> None:
        orders = FakeOrders({})
        use_case, uow, _payments, _, _, wallet, _events = _build(orders=orders)

        with pytest.raises(PaymentOrderNotFoundError):
            use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))
        assert wallet.debits == []
        assert uow.rolled_back is True

    def test_another_shoppers_order_is_indistinguishable_from_unknown(self) -> None:
        orders = FakeOrders({("u:99", _ORDER_NUMBER): _payable()})
        use_case, *_rest, wallet, _events = _build(orders=orders)

        with pytest.raises(PaymentOrderNotFoundError):
            use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))
        assert wallet.debits == []

    @pytest.mark.parametrize("status", ["paid", "cancelled", "fulfilled"])
    def test_rejects_a_non_pending_order(self, status: str) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(status=status)})
        use_case, uow, _, _, _, wallet, _events = _build(orders=orders)

        with pytest.raises(OrderNotPayableError):
            use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))
        assert wallet.debits == []
        assert uow.rolled_back is True

    def test_rejects_a_second_active_payment(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable()})
        payments = FakePayments().with_active(_OWNER, _ORDER_NUMBER, _existing_payment())
        use_case, uow, _, _, _, wallet, _events = _build(orders=orders, payments=payments)

        with pytest.raises(PaymentAlreadyExistsError):
            use_case.execute(PayWithWalletCommand(owner=_OWNER, order_number=_ORDER_NUMBER))
        assert wallet.debits == []
        assert uow.rolled_back is True


def _existing_payment() -> Payment:
    return Payment(
        reference=PaymentReference("PAY-EXIST0"),
        order_ref=OrderRef(_ORDER_NUMBER),
        owner=_OWNER,
        method=PaymentMethod.WALLET,
        amount=Money(amount=Decimal("150.00"), currency="IRR"),
        status=PaymentStatus.CAPTURED,
        created_at=datetime(2026, 7, 5, tzinfo=UTC),
    )
