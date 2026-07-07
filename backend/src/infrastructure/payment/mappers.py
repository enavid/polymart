"""Mapping between the Payment domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.payment.entities import Payment
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)
from src.infrastructure.payment.models import PaymentModel


def _owner_id(model: PaymentModel) -> str:
    """Rebuild the application's opaque, prefixed owner id from the payment's columns.

    ``u:<pk>`` for a user payment, ``g:<token>`` for a guest payment -- the same encoding
    the cart/order contexts use and the HTTP boundary produces, so the domain owns one
    stable string id regardless of which column stores it.
    """
    if model.owner_id is not None:
        return f"u:{model.owner_id}"
    return f"g:{model.guest_token}"


def payment_to_domain(model: PaymentModel) -> Payment:
    """Rebuild the aggregate from a persisted payment row."""
    return Payment(
        reference=PaymentReference(model.reference),
        order_ref=OrderRef(model.order_number),
        owner=_owner_id(model),
        method=PaymentMethod(model.method),
        amount=Money(amount=model.amount, currency=model.currency_code),
        status=PaymentStatus(model.status),
        created_at=model.created_at,
        gateway_reference=model.gateway_reference,
        transfer_reference=model.transfer_reference,
        id=model.pk,
    )
