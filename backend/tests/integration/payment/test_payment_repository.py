"""Integration tests for the Django payment repository + order reader (real DB).

These prove the persistence mapping round-trips, that reads are owner-scoped, that the
"at most one active payment per order" partial constraint is enforced by the database
(the anti-double-payment guarantee), and that the order reader bridges to the order
context owner-scoped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import PaymentAlreadyExistsError, PaymentNotFoundError
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)
from src.infrastructure.order.models import OrderLineModel, OrderModel
from src.infrastructure.payment.models import PaymentModel
from src.infrastructure.payment.repositories import (
    DjangoOrderReader,
    DjangoPaidOrders,
    DjangoPaymentRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_ORDER_NUMBER = "ORD-ABCDEFGH1234"


def _user(phone: str = "09120000001"):
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _owner(user: object) -> str:
    return f"u:{user.pk}"


def _seed_order(
    *,
    owner_pk: int | None = None,
    guest_token: str | None = None,
    number: str = _ORDER_NUMBER,
    total: str = "150.00",
    status: str = "pending",
) -> None:
    OrderModel.objects.create(
        number=number,
        owner_id=owner_pk,
        guest_token=guest_token,
        channel_slug="default",
        currency_code="IRR",
        total=Decimal(total),
        status=status,
        placed_at=datetime(2026, 7, 5, tzinfo=UTC),
        shipping_recipient_name="Sara",
        shipping_phone_number="+989123456789",
        shipping_province="Tehran",
        shipping_city="Tehran",
        shipping_postal_code="1234567890",
        shipping_line1="Valiasr St",
    )


def _payment(
    owner: str,
    *,
    reference: str = "PAY-ABCDEFGH1234",
    order_number: str = _ORDER_NUMBER,
    status: PaymentStatus = PaymentStatus.PENDING,
    total: str = "150.00",
) -> Payment:
    return Payment(
        reference=PaymentReference(reference),
        order_ref=OrderRef(order_number),
        owner=owner,
        method=PaymentMethod.COD,
        amount=Money(amount=Decimal(total), currency="IRR"),
        status=status,
        created_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )


class TestPaymentRepositoryRoundTrip:
    def test_persists_and_reloads_a_user_payment(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()

        saved = repo.add(_payment(_owner(user)))

        assert saved.id is not None
        assert str(PaymentModel.objects.get(reference="PAY-ABCDEFGH1234")) == "PAY-ABCDEFGH1234"
        reloaded = repo.get_for_owner(_owner(user), "PAY-ABCDEFGH1234")
        assert reloaded.reference.value == "PAY-ABCDEFGH1234"
        assert reloaded.order_ref.value == _ORDER_NUMBER
        assert reloaded.owner == _owner(user)
        assert reloaded.method is PaymentMethod.COD
        assert reloaded.amount == Money(amount=Decimal("150.00"), currency="IRR")
        assert reloaded.status is PaymentStatus.PENDING

    def test_persists_and_reloads_a_guest_payment(self) -> None:
        repo = DjangoPaymentRepository()
        owner = "g:guesttoken123"

        repo.add(_payment(owner))

        reloaded = repo.get_for_owner(owner, "PAY-ABCDEFGH1234")
        assert reloaded.owner == owner

    def test_get_for_owner_is_owner_scoped(self) -> None:
        user = _user()
        other = _user(phone="09120000002")
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user)))

        with pytest.raises(PaymentNotFoundError):
            repo.get_for_owner(_owner(other), "PAY-ABCDEFGH1234")

    def test_get_for_order_returns_the_owner_payment(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user)))

        got = repo.get_for_order(_owner(user), _ORDER_NUMBER)
        assert got.reference.value == "PAY-ABCDEFGH1234"

    def test_get_for_order_is_owner_scoped(self) -> None:
        user = _user()
        other = _user(phone="09120000002")
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user)))

        with pytest.raises(PaymentNotFoundError):
            repo.get_for_order(_owner(other), _ORDER_NUMBER)


class TestActivePaymentGuard:
    def test_active_for_order_finds_a_pending_payment(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user)))

        active = repo.active_for_order(_owner(user), _ORDER_NUMBER)
        assert active is not None
        assert active.status is PaymentStatus.PENDING

    def test_active_for_order_ignores_a_spent_payment(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user), status=PaymentStatus.CANCELLED))

        assert repo.active_for_order(_owner(user), _ORDER_NUMBER) is None

    def test_database_rejects_a_second_active_payment_for_the_order(self) -> None:
        # The partial unique constraint is the anti-double-payment guarantee: even if the
        # application-layer guard were bypassed (a race), the DB refuses the second row.
        user = _user()
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user), reference="PAY-FIRST0000001"))

        with pytest.raises(PaymentAlreadyExistsError):
            repo.add(_payment(_owner(user), reference="PAY-SECOND000002"))

    def test_a_fresh_payment_is_allowed_after_a_spent_one(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user), reference="PAY-FAILED000001", status=PaymentStatus.FAILED))

        # A new active payment is allowed because the failed one no longer holds the order.
        saved = repo.add(_payment(_owner(user), reference="PAY-FRESH0000002"))
        assert saved.status is PaymentStatus.PENDING


class TestOrderReader:
    def test_reads_a_pending_user_order(self) -> None:
        user = _user()
        _seed_order(owner_pk=user.pk, total="99.50")

        payable = DjangoOrderReader().get_payable(_owner(user), _ORDER_NUMBER)
        assert payable is not None
        assert payable.number == _ORDER_NUMBER
        assert payable.currency == "IRR"
        assert payable.total == Decimal("99.50")
        assert payable.status == "pending"

    def test_reads_a_guest_order(self) -> None:
        _seed_order(guest_token="gtok123", total="10.00")

        payable = DjangoOrderReader().get_payable("g:gtok123", _ORDER_NUMBER)
        assert payable is not None
        assert payable.total == Decimal("10.00")

    def test_another_owners_order_is_not_found(self) -> None:
        user = _user()
        other = _user(phone="09120000002")
        _seed_order(owner_pk=user.pk)

        assert DjangoOrderReader().get_payable(_owner(other), _ORDER_NUMBER) is None

    def test_unknown_order_is_not_found(self) -> None:
        user = _user()
        assert DjangoOrderReader().get_payable(_owner(user), "ORD-DOESNOTEXIST0") is None


def _seed_order_line(order_number: str = _ORDER_NUMBER) -> None:
    """Attach one line to a seeded order so it rebuilds into a valid Order aggregate."""
    order = OrderModel.objects.get(number=order_number)
    OrderLineModel.objects.create(
        order=order,
        sku="HB-250",
        quantity=1,
        unit_price=Decimal("150.00"),
        line_total=Decimal("150.00"),
        position=0,
    )


class TestOnlineCaptureRepository:
    def test_gateway_reference_round_trips(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        payment = _payment(_owner(user))
        payment = payment.with_gateway_reference("AUTH-XYZ-1")

        repo.add(payment)
        reloaded = repo.get_for_owner(_owner(user), "PAY-ABCDEFGH1234")
        assert reloaded.gateway_reference == "AUTH-XYZ-1"

    def test_get_by_gateway_reference_finds_it(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        repo.add(_payment(_owner(user)).with_gateway_reference("AUTH-1"))

        # Not owner-scoped: a callback resolves the payment by authority alone.
        found = repo.get_by_gateway_reference_for_update("AUTH-1")
        assert found is not None
        assert found.reference.value == "PAY-ABCDEFGH1234"
        assert repo.get_by_gateway_reference_for_update("NOPE") is None

    def test_update_status_persists_the_new_status(self) -> None:
        user = _user()
        repo = DjangoPaymentRepository()
        saved = repo.add(_payment(_owner(user)).with_gateway_reference("AUTH-1"))

        repo.update_status(saved.capture())
        reloaded = repo.get_for_owner(_owner(user), "PAY-ABCDEFGH1234")
        assert reloaded.status is PaymentStatus.CAPTURED


class TestDjangoPaidOrders:
    def test_marks_a_pending_order_paid(self) -> None:
        user = _user()
        _seed_order(owner_pk=user.pk)
        _seed_order_line()

        DjangoPaidOrders().mark_paid(_ORDER_NUMBER)

        assert OrderModel.objects.get(number=_ORDER_NUMBER).status == "paid"

    def test_is_idempotent_on_an_already_paid_order(self) -> None:
        user = _user()
        _seed_order(owner_pk=user.pk, status="paid")
        _seed_order_line()

        DjangoPaidOrders().mark_paid(_ORDER_NUMBER)  # no-op, no error
        assert OrderModel.objects.get(number=_ORDER_NUMBER).status == "paid"

    def test_refuses_to_pay_a_cancelled_order(self) -> None:
        from src.domain.order.exceptions import IllegalOrderTransitionError

        user = _user()
        _seed_order(owner_pk=user.pk, status="cancelled")
        _seed_order_line()

        with pytest.raises(IllegalOrderTransitionError):
            DjangoPaidOrders().mark_paid(_ORDER_NUMBER)
