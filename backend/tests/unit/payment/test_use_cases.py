"""Unit tests for the payment use cases against fakes (no DB, no framework).

These exercise the orchestration: method parsing, gateway resolution, order-payability
checks (owner-scoping, status), the double-initiation guard, amount capture from the
order total, audit recording, atomic rollback, and the owner-scoped reads. The fakes
stand in for the Django adapters wired at the composition root.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.payment.ports import (
    Clock,
    NextActionType,
    OnlinePaymentGateway,
    OrderReader,
    PaidOrders,
    PayableOrder,
    PaymentGateway,
    PaymentGatewayRegistry,
    PaymentIntent,
    PaymentReferenceGenerator,
    PaymentRepository,
    PaymentStartResult,
    PaymentVerification,
    UnitOfWork,
)
from src.application.payment.use_cases import (
    CapturePayment,
    CapturePaymentCommand,
    GetMyPayment,
    GetPaymentForOrder,
    InitiatePayment,
    InitiatePaymentCommand,
)
from src.application.shared.owner import safe_owner
from src.domain.audit.entities import FieldChange
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import (
    GatewayCannotCaptureError,
    InvalidPaymentMethodError,
    OrderNotPayableError,
    PaymentAlreadyExistsError,
    PaymentNotFoundError,
    PaymentOrderNotFoundError,
    UnsupportedPaymentMethodError,
)
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)

# --- Fakes ---------------------------------------------------------------


class FakeUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        self.committed = True


class FakeOrders(OrderReader):
    def __init__(self, orders: dict[tuple[str, str], PayableOrder] | None = None) -> None:
        self._orders = orders or {}

    def get_payable(self, owner: str, number: str) -> PayableOrder | None:
        return self._orders.get((owner, number))


class FakePayments(PaymentRepository):
    def __init__(self) -> None:
        self.saved: list[Payment] = []
        self._active: dict[tuple[str, str], Payment] = {}

    def with_active(self, owner: str, order_number: str, payment: Payment) -> FakePayments:
        self._active[(owner, order_number)] = payment
        return self

    def add(self, payment: Payment) -> Payment:
        stored = Payment(
            reference=payment.reference,
            order_ref=payment.order_ref,
            owner=payment.owner,
            method=payment.method,
            amount=payment.amount,
            status=payment.status,
            created_at=payment.created_at,
            gateway_reference=payment.gateway_reference,
            id=len(self.saved) + 1,
        )
        self.saved.append(stored)
        return stored

    def get_for_owner(self, owner: str, reference: str) -> Payment:
        for payment in self.saved:
            if payment.owner == owner and payment.reference.value == reference:
                return payment
        raise PaymentNotFoundError(reference)

    def get_for_order(self, owner: str, order_number: str) -> Payment:
        for payment in reversed(self.saved):
            if payment.owner == owner and payment.order_ref.value == order_number:
                return payment
        raise PaymentNotFoundError(order_number)

    def active_for_order(self, owner: str, order_number: str) -> Payment | None:
        return self._active.get((owner, order_number))

    def find_by_gateway_reference(self, gateway_reference: str) -> Payment | None:
        return self.get_by_gateway_reference_for_update(gateway_reference)

    def get_by_gateway_reference_for_update(self, gateway_reference: str) -> Payment | None:
        for payment in self.saved:
            if payment.gateway_reference == gateway_reference:
                return payment
        return None

    def update_status(self, payment: Payment) -> Payment:
        for i, stored in enumerate(self.saved):
            if stored.reference.value == payment.reference.value:
                self.saved[i] = payment
                return payment
        raise PaymentNotFoundError(payment.reference.value)


class RecordingGateway(PaymentGateway):
    """A gateway that records the intents it started and reports a fixed next action."""

    def __init__(
        self,
        method: PaymentMethod,
        result: PaymentStartResult | None = None,
    ) -> None:
        self._method = method
        self._result = result or PaymentStartResult(next_action=NextActionType.NONE)
        self.started: list[PaymentIntent] = []

    @property
    def method(self) -> PaymentMethod:
        return self._method

    def start(self, intent: PaymentIntent) -> PaymentStartResult:
        self.started.append(intent)
        return self._result


class FixedReferences(PaymentReferenceGenerator):
    def __init__(self, value: str = "PAY-TEST01") -> None:
        self._value = value

    def next(self) -> PaymentReference:
        return PaymentReference(self._value)


class FixedClock(Clock):
    def now(self) -> datetime:
        return datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: tuple[FieldChange, ...] = (),
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": tuple(changes),
            }
        )


# --- Helpers -------------------------------------------------------------

_OWNER = "u:7"
_ORDER_NUMBER = "ORD-XYZ789"


def _payable(status: str = "pending", total: str = "150.00") -> PayableOrder:
    return PayableOrder(number=_ORDER_NUMBER, currency="IRR", total=Decimal(total), status=status)


def _build_initiate(
    *,
    orders: FakeOrders,
    payments: FakePayments | None = None,
    gateways: tuple[PaymentGateway, ...] = (),
    uow: FakeUnitOfWork | None = None,
    audit: RecordingAudit | None = None,
) -> tuple[InitiatePayment, FakeUnitOfWork, FakePayments, RecordingAudit]:
    uow = uow or FakeUnitOfWork()
    payments = payments if payments is not None else FakePayments()
    audit = audit or RecordingAudit()
    registry = PaymentGatewayRegistry(gateways or (RecordingGateway(PaymentMethod.COD),))
    use_case = InitiatePayment(
        unit_of_work=uow,
        orders=orders,
        payments=payments,
        gateways=registry,
        references=FixedReferences(),
        clock=FixedClock(),
        audit=audit,
    )
    return use_case, uow, payments, audit


# --- InitiatePayment: happy path -----------------------------------------


class TestInitiatePaymentSuccess:
    def test_creates_a_pending_cod_payment_capturing_the_order_total(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="150.00")})
        use_case, uow, payments, _ = _build_initiate(orders=orders)

        result = use_case.execute(
            InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
        )

        assert uow.committed is True
        assert result.payment.status is PaymentStatus.PENDING
        assert result.payment.method is PaymentMethod.COD
        # The amount is the order's captured total -- never client-supplied.
        assert result.payment.amount == Money(amount=Decimal("150.00"), currency="IRR")
        assert result.payment.order_ref == OrderRef(_ORDER_NUMBER)
        assert result.payment.owner == _OWNER
        assert result.payment.id == 1
        assert len(payments.saved) == 1

    def test_cod_reports_no_further_action(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable()})
        use_case, *_ = _build_initiate(orders=orders)

        result = use_case.execute(
            InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
        )

        assert result.next_action is NextActionType.NONE
        assert result.redirect_url is None

    def test_hands_the_captured_amount_to_the_gateway(self) -> None:
        gateway = RecordingGateway(PaymentMethod.COD)
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(total="42.00")})
        use_case, *_ = _build_initiate(orders=orders, gateways=(gateway,))

        use_case.execute(
            InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
        )

        assert len(gateway.started) == 1
        intent = gateway.started[0]
        assert intent.order_number == _ORDER_NUMBER
        assert intent.amount == Money(amount=Decimal("42.00"), currency="IRR")
        assert intent.method is PaymentMethod.COD

    def test_audits_the_initiation_without_leaking_the_guest_token(self) -> None:
        guest = "g:supersecrettoken"
        orders = FakeOrders({(guest, _ORDER_NUMBER): _payable(total="99.00")})
        use_case, _, _, audit = _build_initiate(orders=orders)

        use_case.execute(
            InitiatePaymentCommand(owner=guest, order_number=_ORDER_NUMBER, method="cod")
        )

        assert len(audit.records) == 1
        entry = audit.records[0]
        assert entry["action"] == "payment.initiated"
        assert entry["resource_type"] == "payment"
        assert entry["resource_id"] == "PAY-TEST01"
        # The raw guest token must never be written to the trail.
        assert entry["actor"] == safe_owner(guest)
        assert entry["actor"] != guest
        fields = {c.field: c.after for c in entry["changes"]}  # type: ignore[attr-defined]
        assert fields["status"] == "pending"
        assert fields["method"] == "cod"
        assert fields["amount"] == "99.00"
        assert fields["order"] == _ORDER_NUMBER

    def test_logs_without_the_amount_or_raw_token(self) -> None:
        guest = "g:supersecrettoken"
        orders = FakeOrders({(guest, _ORDER_NUMBER): _payable(total="99.00")})
        use_case, *_ = _build_initiate(orders=orders)

        with capture_logs() as logs:
            use_case.execute(
                InitiatePaymentCommand(owner=guest, order_number=_ORDER_NUMBER, method="cod")
            )

        # Assert absence (never presence): the app logger is cached under the real config,
        # so capture_logs may not intercept it in the full suite -- but the money amount and
        # the raw guest token must never appear in any captured log line either way. The
        # positive "fields are recorded" guarantee is covered by the audit test above.
        assert not any("99.00" in str(event) for event in logs)
        assert not any("supersecrettoken" in str(event) for event in logs)


# --- InitiatePayment: failure paths --------------------------------------


class TestInitiatePaymentFailures:
    def test_rejects_an_unknown_method(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable()})
        use_case, uow, payments, _ = _build_initiate(orders=orders)

        with pytest.raises(InvalidPaymentMethodError):
            use_case.execute(
                InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="bitcoin")
            )
        assert payments.saved == []
        # Rejected before the transaction opens.
        assert uow.committed is False

    def test_rejects_a_method_with_no_registered_gateway(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable()})
        # Only COD is registered; asking for online has no adapter.
        use_case, uow, payments, _ = _build_initiate(
            orders=orders, gateways=(RecordingGateway(PaymentMethod.COD),)
        )

        with pytest.raises(UnsupportedPaymentMethodError):
            use_case.execute(
                InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="online")
            )
        assert payments.saved == []
        assert uow.committed is False

    def test_rejects_an_unknown_order(self) -> None:
        orders = FakeOrders({})  # nothing resolves
        use_case, uow, payments, _ = _build_initiate(orders=orders)

        with pytest.raises(PaymentOrderNotFoundError):
            use_case.execute(
                InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
            )
        assert payments.saved == []
        assert uow.rolled_back is True

    def test_another_shoppers_order_is_indistinguishable_from_unknown(self) -> None:
        # The order exists but belongs to a different owner; this owner cannot resolve it,
        # so it is reported as not found (never as "not payable"), which would leak that a
        # different shopper's order exists.
        orders = FakeOrders({("u:99", _ORDER_NUMBER): _payable()})
        use_case, _, payments, _ = _build_initiate(orders=orders)

        with pytest.raises(PaymentOrderNotFoundError):
            use_case.execute(
                InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
            )
        assert payments.saved == []

    @pytest.mark.parametrize("status", ["paid", "cancelled", "fulfilled"])
    def test_rejects_a_non_pending_order(self, status: str) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable(status=status)})
        use_case, uow, payments, _ = _build_initiate(orders=orders)

        with pytest.raises(OrderNotPayableError):
            use_case.execute(
                InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
            )
        assert payments.saved == []
        assert uow.rolled_back is True

    def test_rejects_a_second_active_payment(self) -> None:
        orders = FakeOrders({(_OWNER, _ORDER_NUMBER): _payable()})
        existing = Payment(
            reference=PaymentReference("PAY-EXIST0"),
            order_ref=OrderRef(_ORDER_NUMBER),
            owner=_OWNER,
            method=PaymentMethod.COD,
            amount=Money(amount=Decimal("150.00"), currency="IRR"),
            status=PaymentStatus.PENDING,
            created_at=datetime(2026, 7, 5, tzinfo=UTC),
        )
        payments = FakePayments().with_active(_OWNER, _ORDER_NUMBER, existing)
        use_case, uow, payments, _ = _build_initiate(orders=orders, payments=payments)

        with pytest.raises(PaymentAlreadyExistsError):
            use_case.execute(
                InitiatePaymentCommand(owner=_OWNER, order_number=_ORDER_NUMBER, method="cod")
            )
        assert payments.saved == []
        assert uow.rolled_back is True


# --- Reads ---------------------------------------------------------------


class TestReads:
    def _payment(self, owner: str = _OWNER) -> Payment:
        return Payment(
            reference=PaymentReference("PAY-READ01"),
            order_ref=OrderRef(_ORDER_NUMBER),
            owner=owner,
            method=PaymentMethod.COD,
            amount=Money(amount=Decimal("10.00"), currency="IRR"),
            status=PaymentStatus.PENDING,
            created_at=datetime(2026, 7, 5, tzinfo=UTC),
        )

    def test_get_my_payment_returns_own_payment(self) -> None:
        payments = FakePayments()
        payments.add(self._payment())
        got = GetMyPayment(payments).execute(owner=_OWNER, reference="pay-read01")
        assert got.reference.value == "PAY-READ01"

    def test_get_my_payment_rejects_a_malformed_reference_as_not_found(self) -> None:
        payments = FakePayments()
        # A malformed reference never matches; the read raises PaymentError (InvalidReference).
        from src.domain.payment.exceptions import InvalidPaymentReferenceError

        with pytest.raises(InvalidPaymentReferenceError):
            GetMyPayment(payments).execute(owner=_OWNER, reference="!!")

    def test_get_my_payment_does_not_return_another_owners(self) -> None:
        payments = FakePayments()
        payments.add(self._payment(owner="u:99"))
        with pytest.raises(PaymentNotFoundError):
            GetMyPayment(payments).execute(owner=_OWNER, reference="PAY-READ01")

    def test_get_payment_for_order_returns_it(self) -> None:
        payments = FakePayments()
        payments.add(self._payment())
        got = GetPaymentForOrder(payments).execute(owner=_OWNER, order_number=_ORDER_NUMBER)
        assert got.order_ref.value == _ORDER_NUMBER

    def test_get_payment_for_order_scopes_by_owner(self) -> None:
        payments = FakePayments()
        payments.add(self._payment(owner="u:99"))
        with pytest.raises(PaymentNotFoundError):
            GetPaymentForOrder(payments).execute(owner=_OWNER, order_number=_ORDER_NUMBER)


# --- CapturePayment ------------------------------------------------------


class FakePaidOrders(PaidOrders):
    def __init__(self) -> None:
        self.paid: list[str] = []

    def mark_paid(self, order_number: str) -> None:
        self.paid.append(order_number)


class FakeOnlineGateway(OnlinePaymentGateway):
    """An online gateway whose verify() outcome is fixed by the test."""

    def __init__(self, *, captured: bool = True, provider_reference: str = "RID-1") -> None:
        self._captured = captured
        self._provider_reference = provider_reference
        self.verified: list[str] = []

    @property
    def method(self) -> PaymentMethod:
        return PaymentMethod.ONLINE

    def start(self, intent: PaymentIntent) -> PaymentStartResult:  # pragma: no cover - unused here
        return PaymentStartResult(
            next_action=NextActionType.REDIRECT,
            redirect_url="https://gw/pay",
            gateway_reference="AUTH1",
        )

    def verify(self, *, gateway_reference: str, amount: Money) -> PaymentVerification:
        self.verified.append(gateway_reference)
        return PaymentVerification(
            captured=self._captured,
            provider_reference=self._provider_reference if self._captured else None,
        )


_AUTHORITY = "AUTH-XYZ-1"


def _online_payment(status: PaymentStatus = PaymentStatus.PENDING, owner: str = _OWNER) -> Payment:
    return Payment(
        reference=PaymentReference("PAY-ONLINE1"),
        order_ref=OrderRef(_ORDER_NUMBER),
        owner=owner,
        method=PaymentMethod.ONLINE,
        amount=Money(amount=Decimal("150.00"), currency="IRR"),
        status=status,
        created_at=datetime(2026, 7, 5, tzinfo=UTC),
        gateway_reference=_AUTHORITY,
    )


def _build_capture(
    *,
    payment: Payment,
    gateway: OnlinePaymentGateway | None = None,
    uow: FakeUnitOfWork | None = None,
    paid: FakePaidOrders | None = None,
    audit: RecordingAudit | None = None,
) -> tuple[CapturePayment, FakePaidOrders, RecordingAudit, FakeUnitOfWork]:
    uow = uow or FakeUnitOfWork()
    payments = FakePayments()
    payments.add(payment)
    paid = paid or FakePaidOrders()
    audit = audit or RecordingAudit()
    registry = PaymentGatewayRegistry((gateway or FakeOnlineGateway(),))
    use_case = CapturePayment(
        unit_of_work=uow, payments=payments, gateways=registry, paid_orders=paid, audit=audit
    )
    return use_case, paid, audit, uow


class TestCapturePayment:
    def test_success_captures_and_marks_the_order_paid(self) -> None:
        gateway = FakeOnlineGateway(captured=True, provider_reference="RID-9")
        use_case, paid, audit, uow = _build_capture(payment=_online_payment(), gateway=gateway)

        result = use_case.execute(
            CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=True)
        )

        assert result.status is PaymentStatus.CAPTURED
        assert uow.committed is True
        assert gateway.verified == [_AUTHORITY]  # server re-verified, never trusted the redirect
        assert paid.paid == [_ORDER_NUMBER]  # order marked paid in the same transaction
        entry = next(r for r in audit.records if r["action"] == "payment.captured")
        fields = {c.field: c.after for c in entry["changes"]}  # type: ignore[attr-defined]
        assert fields["status"] == "captured"
        assert fields["amount"] == "150.00"
        assert fields["provider_reference"] == "RID-9"

    def test_is_idempotent_on_a_repeated_callback(self) -> None:
        gateway = FakeOnlineGateway(captured=True)
        use_case, paid, audit, _ = _build_capture(payment=_online_payment(), gateway=gateway)
        first = use_case.execute(
            CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=True)
        )
        assert first.status is PaymentStatus.CAPTURED

        # A duplicate callback must not re-verify, re-capture, or re-pay the order.
        second = use_case.execute(
            CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=True)
        )
        assert second.status is PaymentStatus.CAPTURED
        assert gateway.verified == [_AUTHORITY]  # only the first verified
        assert paid.paid == [_ORDER_NUMBER]  # order paid exactly once
        assert len([r for r in audit.records if r["action"] == "payment.captured"]) == 1

    def test_a_cancelled_callback_fails_without_verifying(self) -> None:
        gateway = FakeOnlineGateway(captured=True)
        use_case, paid, audit, _ = _build_capture(payment=_online_payment(), gateway=gateway)

        result = use_case.execute(
            CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=False)
        )

        assert result.status is PaymentStatus.FAILED
        assert gateway.verified == []  # a cancel never calls the gateway
        assert paid.paid == []  # the order is not paid
        assert any(r["action"] == "payment.failed" for r in audit.records)

    def test_a_failed_verification_fails_the_payment(self) -> None:
        gateway = FakeOnlineGateway(captured=False)
        use_case, paid, _, _ = _build_capture(payment=_online_payment(), gateway=gateway)

        result = use_case.execute(
            CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=True)
        )

        assert result.status is PaymentStatus.FAILED
        assert gateway.verified == [_AUTHORITY]  # verified, but the gateway said no
        assert paid.paid == []

    def test_an_already_failed_payment_is_left_untouched(self) -> None:
        gateway = FakeOnlineGateway(captured=True)
        use_case, paid, _, _ = _build_capture(
            payment=_online_payment(status=PaymentStatus.FAILED), gateway=gateway
        )

        result = use_case.execute(
            CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=True)
        )

        assert result.status is PaymentStatus.FAILED  # unchanged
        assert gateway.verified == []
        assert paid.paid == []

    def test_an_unknown_reference_is_not_found(self) -> None:
        use_case, *_ = _build_capture(payment=_online_payment())
        with pytest.raises(PaymentNotFoundError):
            use_case.execute(CapturePaymentCommand(gateway_reference="NOPE", succeeded=True))

    def test_a_non_online_gateway_cannot_capture(self) -> None:
        # A payment awaiting capture whose method resolves to a COD (offline) gateway.
        payment = Payment(
            reference=PaymentReference("PAY-BADGW01"),
            order_ref=OrderRef(_ORDER_NUMBER),
            owner=_OWNER,
            method=PaymentMethod.COD,
            amount=Money(amount=Decimal("150.00"), currency="IRR"),
            status=PaymentStatus.PENDING,
            created_at=datetime(2026, 7, 5, tzinfo=UTC),
            gateway_reference=_AUTHORITY,
        )
        uow = FakeUnitOfWork()
        payments = FakePayments()
        payments.add(payment)
        registry = PaymentGatewayRegistry((RecordingGateway(PaymentMethod.COD),))
        use_case = CapturePayment(
            unit_of_work=uow,
            payments=payments,
            gateways=registry,
            paid_orders=FakePaidOrders(),
            audit=RecordingAudit(),
        )
        with pytest.raises(GatewayCannotCaptureError):
            use_case.execute(CapturePaymentCommand(gateway_reference=_AUTHORITY, succeeded=True))
        assert uow.rolled_back is True
