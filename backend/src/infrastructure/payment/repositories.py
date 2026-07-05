"""Django ORM implementation of the payment ports.

The payment repository persists and reloads the aggregate; the order reader bridges to the
neighbouring order context. All reads a use case uses to resolve a payment are
owner-scoped, so one shopper can never reach another's payment (or, via the order reader,
pay against another shopper's order).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

import structlog
from django.db import IntegrityError, transaction

from src.application.payment.ports import (
    OrderReader,
    PaidOrders,
    PayableOrder,
    PaymentRepository,
    UnitOfWork,
)
from src.domain.order.value_objects import OrderStatus
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import PaymentAlreadyExistsError, PaymentNotFoundError
from src.domain.payment.value_objects import ACTIVE_PAYMENT_STATUSES
from src.infrastructure.order.mappers import order_to_domain
from src.infrastructure.order.models import OrderModel
from src.infrastructure.payment.mappers import payment_to_domain
from src.infrastructure.payment.models import PaymentModel

logger = structlog.get_logger(__name__)

_ACTIVE_STATUS_VALUES = tuple(status.value for status in ACTIVE_PAYMENT_STATUSES)


def _owner_filter(owner: str) -> dict[str, Any]:
    """Map the application's opaque owner id to the columns that identify it.

    ``u:<pk>`` -> the user FK (``owner_id``); ``g:<token>`` -> the ``guest_token`` column.
    Mirrors the cart/order decode and the encoding produced at the HTTP boundary, so the
    domain's stable string id stays independent of the database's key types.
    """
    kind, _, value = owner.partition(":")
    if kind == "u":
        return {"owner_id": int(value)}
    if kind == "g":
        return {"guest_token": value}
    raise ValueError(f"unrecognized payment owner id: {owner!r}")  # pragma: no cover - defensive


class DjangoPaymentRepository(PaymentRepository):
    """Persist payments with the Django ORM, returning domain aggregates."""

    def add(self, payment: Payment) -> Payment:
        try:
            model = PaymentModel.objects.create(
                reference=payment.reference.value,
                order_number=payment.order_ref.value,
                **_owner_filter(payment.owner),
                method=payment.method.value,
                gateway_reference=payment.gateway_reference,
                amount=payment.amount.amount,
                currency_code=payment.amount.currency,
                status=payment.status.value,
                created_at=payment.created_at,
            )
        except IntegrityError as exc:
            # The partial unique (at most one active payment per order) is the meaningful
            # collision: two initiations raced and this one lost. Translate to the domain's
            # double-initiation error so the transport maps it to 409 (the reference unique
            # cannot realistically collide -- it is CSPRNG-wide).
            raise PaymentAlreadyExistsError(payment.order_ref.value) from exc
        return payment_to_domain(model)

    def get_for_owner(self, owner: str, reference: str) -> Payment:
        try:
            model = PaymentModel.objects.get(reference=reference, **_owner_filter(owner))
        except PaymentModel.DoesNotExist as exc:
            raise PaymentNotFoundError(reference) from exc
        return payment_to_domain(model)

    def get_for_order(self, owner: str, order_number: str) -> Payment:
        # Meta.ordering is newest-first ("-id"), so the most recent attempt is returned.
        model = (
            PaymentModel.objects.filter(order_number=order_number, **_owner_filter(owner))
            .order_by("-id")
            .first()
        )
        if model is None:
            raise PaymentNotFoundError(order_number)
        return payment_to_domain(model)

    def active_for_order(self, owner: str, order_number: str) -> Payment | None:
        model = PaymentModel.objects.filter(
            order_number=order_number,
            status__in=_ACTIVE_STATUS_VALUES,
            **_owner_filter(owner),
        ).first()
        if model is None:
            return None
        return payment_to_domain(model)

    def find_by_gateway_reference(self, gateway_reference: str) -> Payment | None:
        model = PaymentModel.objects.filter(gateway_reference=gateway_reference).first()
        if model is None:
            return None
        return payment_to_domain(model)

    def get_by_gateway_reference_for_update(self, gateway_reference: str) -> Payment | None:
        # Not owner-scoped: a gateway callback carries only the unguessable authority, no
        # user session. The row lock serializes concurrent callbacks so only one captures
        # (the second observes the already-captured status and no-ops).
        model = (
            PaymentModel.objects.select_for_update()
            .filter(gateway_reference=gateway_reference)
            .first()
        )
        if model is None:
            return None
        return payment_to_domain(model)

    def get_by_reference_for_update(self, reference: str) -> Payment | None:
        # Not owner-scoped: refund is a staff action addressed by the payment's public
        # reference (gated by the manage-orders permission at the transport). The row lock
        # serializes concurrent refunds so only one transitions captured -> refunded.
        model = (
            PaymentModel.objects.select_for_update().filter(reference=reference).first()
        )
        if model is None:
            return None
        return payment_to_domain(model)

    def update_status(self, payment: Payment) -> Payment:
        PaymentModel.objects.filter(reference=payment.reference.value).update(
            status=payment.status.value
        )
        model = PaymentModel.objects.get(reference=payment.reference.value)
        return payment_to_domain(model)


class DjangoOrderReader(OrderReader):
    """Read a shopper's order from the order context, for the amount and payability check.

    Owner-scoped: an order belonging to another owner (or that does not exist at all)
    resolves to ``None``, so payment can never reveal whether another shopper's order
    exists and the charged amount is always the server's captured total.
    """

    def get_payable(self, owner: str, number: str) -> PayableOrder | None:
        row = (
            OrderModel.objects.filter(number=number, **_owner_filter(owner))
            .values("number", "currency_code", "total", "status")
            .first()
        )
        if row is None:
            return None
        return PayableOrder(
            number=row["number"],
            currency=row["currency_code"],
            total=row["total"],
            status=row["status"],
        )


class DjangoPaidOrders(PaidOrders):
    """Mark an order paid when its payment captures, driving the order's own state machine.

    Runs inside the capture use case's transaction, so the order flips to ``paid`` atomically
    with the payment's capture. The order row is locked (serializing against a concurrent
    cancel), the transition is idempotent (an already-paid order is a no-op), and it goes
    through the order aggregate so an illegal move (e.g. paying a cancelled order) is refused
    -- which rolls the whole capture back.
    """

    def mark_paid(self, order_number: str) -> None:
        try:
            model = (
                OrderModel.objects.select_for_update()
                .prefetch_related("lines")
                .get(number=order_number)
            )
        except OrderModel.DoesNotExist as exc:  # pragma: no cover - defensive
            # A captured payment always has a real order; treat a missing one as not found.
            raise PaymentNotFoundError(order_number) from exc
        if model.status == OrderStatus.PAID.value:
            return  # idempotent: already paid (a duplicate capture path)
        order = order_to_domain(model)
        paid = order.transition_to(OrderStatus.PAID)  # raises if the order is not payable
        OrderModel.objects.filter(number=order_number).update(status=paid.status.value)


class DjangoUnitOfWork(UnitOfWork):
    """Transaction boundary backed by Django's ``transaction.atomic``.

    Everything the initiate use case performs inside ``atomic()`` commits together or rolls
    back together on any exception -- so a failed gateway start or a lost double-initiation
    race leaves no payment and no audit entry behind.
    """

    def atomic(self) -> AbstractContextManager[None]:
        return transaction.atomic()
