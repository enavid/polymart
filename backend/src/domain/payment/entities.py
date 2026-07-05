"""The Payment aggregate: a record of settling one order, with a lifecycle state machine.

A payment captures the amount owed at initiation (a snapshot of the order total, so a
later catalog price change never rewrites what was charged) and moves through a small
state machine that governs which status changes are legal. Identity is the public,
unguessable ``reference``; the owner is the same opaque, prefixed id the cart and order
contexts use (``u:<pk>`` / ``g:<token>``), so a payment is always resolved from the
authenticated shopper (or their guest cookie), never from a client-supplied id.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from src.domain.payment.exceptions import IllegalPaymentTransitionError
from src.domain.payment.value_objects import (
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)

# The payment state machine: which statuses each status may move to. A terminal state
# maps to an empty set. Kept as data (not scattered if/else) so the legal lifecycle is
# declared in one readable place, mirroring the order aggregate's table.
_ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
        }
    ),
    PaymentStatus.AUTHORIZED: frozenset(
        {PaymentStatus.CAPTURED, PaymentStatus.VOIDED, PaymentStatus.FAILED}
    ),
    PaymentStatus.CAPTURED: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.VOIDED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


@dataclass(frozen=True)
class Payment:
    """A shopper's payment against one order.

    Immutable: a status change yields a new instance (``transition_to``) rather than
    mutating in place, so an aggregate never sits in a half-changed state. The amount is
    captured from the order total at initiation; ``created_at`` is tz-aware.
    """

    reference: PaymentReference
    order_ref: OrderRef
    owner: str
    method: PaymentMethod
    amount: Money
    status: PaymentStatus
    created_at: datetime
    id: int | None = field(default=None)

    def transition_to(self, target: PaymentStatus) -> Payment:
        """Return a copy of the payment in ``target`` status, or raise if illegal.

        The aggregate is immutable, so a transition yields a new instance rather than
        mutating in place; the state-machine table is the single source of truth for what
        is allowed.
        """
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise IllegalPaymentTransitionError(self.status.value, target.value)
        return replace(self, status=target)
