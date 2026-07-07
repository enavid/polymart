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


class PaymentNotRefundableError(PaymentError):
    """Raised when a refund is requested for a payment that is not captured.

    Only a captured payment holds funds that can be returned; a pending/failed/cancelled/
    voided one has nothing to refund. The transport maps this to 409 (a conflict with the
    payment's current state). An already-refunded payment is *not* an error -- the refund
    use case treats a repeat as an idempotent no-op.
    """

    def __init__(self, reference: str, status: str) -> None:
        super().__init__(f"payment {reference} is not refundable in status {status!r}")
        self.reference = reference
        self.status = status


class WalletOwnerRequiredError(PaymentError):
    """Raised when a refund-to-wallet targets a payment with no wallet-capable owner.

    A wallet always belongs to a registered user; a guest payment (owner ``g:<token>``) has
    no account to hold store credit, so it cannot be refunded to a wallet (a guest refund
    would return to the gateway -- a later slice). The transport maps this to 409.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"payment {reference} has no wallet-capable owner to refund to")
        self.reference = reference


class WalletPaymentRequiresUserError(PaymentError):
    """Raised when a guest tries to pay with a wallet.

    A wallet always belongs to a registered user; a guest (owner ``g:<token>``) has no
    account to hold or spend store credit, so pay-with-wallet is refused for them. The
    transport maps this to 409 (the request cannot be honoured for a guest).
    """

    def __init__(self) -> None:
        super().__init__("paying with a wallet requires a signed-in account")


class InsufficientWalletBalanceError(PaymentError):
    """Raised when a pay-with-wallet cannot be covered by the shopper's balance.

    The wallet balance is less than the order total (or the wallet does not exist yet), so
    the payment cannot be settled from store credit. The payment context's own error type,
    translated by the wallet-debit adapter so no wallet-domain exception crosses the seam.
    The transport maps this to 409 (a conflict with the wallet's current balance).
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"wallet balance does not cover payment {reference}")
        self.reference = reference


class NotACardToCardPaymentError(PaymentError):
    """Raised when a card-to-card action targets a payment paid by another method.

    Submitting a transfer reference, or confirming/rejecting a transfer, only makes sense for
    a ``card_to_card`` payment. The transport maps this to 409.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"payment {reference} is not a card-to-card payment")
        self.reference = reference


class TransferReferenceAlreadySubmittedError(PaymentError):
    """Raised when a buyer submits a second card-to-card transfer reference.

    A transfer reference is submitted once (a repeat is not an idempotent no-op -- it is the
    buyer trying to change a reported transfer, which staff verification must not allow). The
    transport maps this to 409.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"payment {reference} already has a submitted transfer reference")
        self.reference = reference


class PaymentNotAwaitingTransferError(PaymentError):
    """Raised when a transfer reference is submitted for a payment that is not awaiting one.

    Only a still-pending card-to-card payment accepts a transfer reference; a settled one
    (captured/failed) does not. The transport maps this to 409.
    """

    def __init__(self, reference: str, status: str) -> None:
        super().__init__(f"payment {reference} is not awaiting a transfer in status {status!r}")
        self.reference = reference
        self.status = status


class PaymentNotConfirmableError(PaymentError):
    """Raised when staff confirm/reject a card-to-card payment that is not confirmable.

    Confirmation captures a *pending* card-to-card payment that carries a buyer-submitted
    transfer reference; a payment that is not pending, or that has no reported transfer to
    verify, cannot be confirmed. The transport maps this to 409. An already-captured payment
    (confirm) or already-failed payment (reject) is *not* an error -- it is an idempotent
    no-op.
    """

    def __init__(self, reference: str, reason: str) -> None:
        super().__init__(f"payment {reference} cannot be confirmed: {reason}")
        self.reference = reference
        self.reason = reason


class CardToCardNotConfiguredError(PaymentError):
    """Raised when a channel has no card-to-card destination card configured.

    Card-to-card cannot be offered for an order whose channel has no receiving card set up
    (a server-side configuration gap). The transport maps this to 409.
    """

    def __init__(self, channel: str) -> None:
        super().__init__(f"no card-to-card destination is configured for channel {channel!r}")
        self.channel = channel


class GatewayCannotCaptureError(PaymentError):
    """Raised when a payment awaiting capture is bound to a non-verifiable gateway.

    Capture requires an online gateway (one that can ``verify``); a payment whose method has
    only an offline adapter cannot be captured via the callback path. This is a wiring/logic
    guard, not a normal runtime condition.
    """

    def __init__(self, method: str) -> None:
        super().__init__(f"gateway for method {method!r} cannot capture (not an online gateway)")
        self.method = method
