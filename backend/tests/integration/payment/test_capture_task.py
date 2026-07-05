"""Integration test for the capture Celery task's error handling (eager mode)."""

from __future__ import annotations

import pytest

from src.infrastructure.payment.tasks import capture_online_payment

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_task_swallows_an_unresolvable_reference() -> None:
    # A callback for a payment that no longer resolves is logged and swallowed (returns
    # None) rather than retried forever -- a retry cannot fix a missing payment.
    assert capture_online_payment("MOCK-DOES-NOT-EXIST", succeeded=True) is None


def test_task_rolls_back_and_swallows_when_the_order_cannot_be_paid() -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    from django.contrib.auth import get_user_model

    from src.infrastructure.order.models import OrderLineModel, OrderModel
    from src.infrastructure.payment.models import PaymentModel

    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    order = OrderModel.objects.create(
        number="ORD-CANCELLED0001",
        owner_id=user.pk,
        channel_slug="ir-main",
        currency_code="IRR",
        total=Decimal("150.00"),
        status="cancelled",  # cancelled between initiation and this callback
        placed_at=datetime(2026, 7, 5, tzinfo=UTC),
        shipping_recipient_name="Sara",
        shipping_phone_number="+989123456789",
        shipping_province="Tehran",
        shipping_city="Tehran",
        shipping_postal_code="1234567890",
        shipping_line1="Valiasr St",
    )
    OrderLineModel.objects.create(
        order=order,
        sku="HB-250",
        quantity=1,
        unit_price=Decimal("150.00"),
        line_total=Decimal("150.00"),
        position=0,
    )
    PaymentModel.objects.create(
        reference="PAY-ONLINECANCEL",
        order_number="ORD-CANCELLED0001",
        owner_id=user.pk,
        method="online",
        gateway_reference="AUTH-CANCELLED",
        amount=Decimal("150.00"),
        currency_code="IRR",
        status="pending",
        created_at=datetime(2026, 7, 5, tzinfo=UTC),
    )

    # The gateway verify would capture, but the cancelled order cannot be marked paid, so the
    # whole capture rolls back and the task swallows the error (returns None, no worker crash).
    assert capture_online_payment("AUTH-CANCELLED", succeeded=True) is None
    assert PaymentModel.objects.get(reference="PAY-ONLINECANCEL").status == "pending"
    assert OrderModel.objects.get(number="ORD-CANCELLED0001").status == "cancelled"
