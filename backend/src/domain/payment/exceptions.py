"""Domain exceptions for the payment context.

A single base (``PaymentError``) lets the transport layer catch the whole family and
map it to a sensible default, while the specific subclasses carry the meaning a view
needs to choose a precise status code. Like the order context, a few boundary conditions
that are strictly application concerns (an unknown/unpayable order, an unsupported
method) are modelled here so the use cases raise from one coherent hierarchy.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations


class PaymentError(Exception):
    """Base class for every payment-domain error."""


class InvalidMoneyError(PaymentError):
    """Raised when a monetary amount is not a valid, representable, non-negative value."""


class InvalidPaymentReferenceError(PaymentError):
    """Raised when a payment reference is structurally malformed."""


class InvalidOrderReferenceError(PaymentError):
    """Raised when the referenced order number is structurally malformed."""


class InvalidPaymentMethodError(PaymentError):
    """Raised when a payment method value is not one the platform recognises."""


class IllegalPaymentTransitionError(PaymentError):
    """Raised when a status change is not allowed by the payment state machine."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition a payment from {current!r} to {target!r}")
        self.current = current
        self.target = target


class UnsupportedPaymentMethodError(PaymentError):
    """Raised when no gateway is registered for the requested payment method.

    The method is a valid enum member but the platform has no adapter wired for it yet
    (e.g. online/card-to-card before their gateway slices land), so a payment cannot be
    initiated through it.
    """

    def __init__(self, method: str) -> None:
        super().__init__(f"no payment gateway is available for method {method!r}")
        self.method = method


class PaymentOrderNotFoundError(PaymentError):
    """Raised when the referenced order does not resolve for this owner.

    Either it does not exist, or it is another shopper's -- the two are indistinguishable
    (the reader is owner-scoped), so payment never reveals whether another shopper's order
    id exists. The transport maps this to 404.
    """

    def __init__(self, order_number: str) -> None:
        super().__init__(f"order not found: {order_number}")
        self.order_number = order_number


class OrderNotPayableError(PaymentError):
    """Raised when the owner's order exists but is not in a state that accepts payment.

    The order is the caller's own (owner-scoped), so surfacing its state is not an IDOR
    leak; it is simply already paid, cancelled, or fulfilled. The transport maps this to
    409 (a conflict with the order's current state).
    """

    def __init__(self, order_number: str, status: str) -> None:
        super().__init__(f"order {order_number} is not payable in status {status!r}")
        self.order_number = order_number
        self.status = status


class PaymentAlreadyExistsError(PaymentError):
    """Raised when the order already has an active payment (double-initiation guard).

    An order may hold at most one payment that is still open (pending/authorized/captured)
    at a time; a spent one (failed/cancelled/voided) does not block a fresh attempt.
    """

    def __init__(self, order_number: str) -> None:
        super().__init__(f"order {order_number} already has an active payment")
        self.order_number = order_number


class PaymentNotFoundError(PaymentError):
    """Raised when no payment matches the owner/reference (or owner/order) pair."""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"payment not found: {identifier}")
        self.identifier = identifier
