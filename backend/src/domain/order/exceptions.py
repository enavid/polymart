"""Domain exceptions for the order context.

A single base (``OrderError``) lets the transport layer catch the whole family and
map it to a sensible default, while the specific subclasses carry the meaning a view
needs to choose a precise status code. Like the cart, a few boundary conditions that
are strictly application concerns (an unknown channel, an out-of-stock variant) are
modelled here so the use cases raise from one coherent hierarchy.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations


class OrderError(Exception):
    """Base class for every order-domain error."""


class InvalidMoneyError(OrderError):
    """Raised when a monetary amount is not a valid, representable, non-negative value."""


class InvalidSkuError(OrderError):
    """Raised when a SKU reference is structurally malformed."""


class InvalidOrderQuantityError(OrderError):
    """Raised when an order line quantity is not a positive, bounded integer."""


class InvalidChannelReferenceError(OrderError):
    """Raised when a channel reference is blank or too long."""


class InvalidOrderNumberError(OrderError):
    """Raised when an order number is structurally malformed."""


class InvalidShippingAddressError(OrderError):
    """Raised when a captured shipping address is missing a required field."""


class EmptyOrderError(OrderError):
    """Raised when an order would have no lines -- an order must sell something."""


class DuplicateOrderLineError(OrderError):
    """Raised when the same variant would appear on more than one line of an order."""


class OrderTotalMismatchError(OrderError):
    """Raised when an order's stated total does not equal the sum of its line totals."""


class OrderCurrencyMismatchError(OrderError):
    """Raised when a line's currency differs from the order's currency."""


class IllegalOrderTransitionError(OrderError):
    """Raised when a status change is not allowed by the order state machine."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition an order from {current!r} to {target!r}")
        self.current = current
        self.target = target


class EmptyCartError(OrderError):
    """Raised when checkout is attempted with an empty cart (nothing to order)."""


class UnknownChannelError(OrderError):
    """Raised when checkout references a channel that does not exist."""


class UnknownShippingAddressError(OrderError):
    """Raised when checkout references an address that is not one of the owner's own."""


class UnknownShippingMethodError(OrderError):
    """Raised when checkout references a shipping method the channel does not offer."""

    def __init__(self, channel: str, method: str) -> None:
        super().__init__(f"shipping method {method!r} is not available in channel {channel!r}")
        self.channel = channel
        self.method = method


class InvalidCapturedShippingError(OrderError):
    """Raised when a captured shipping selection is missing a required field."""


class InvalidCapturedTaxError(OrderError):
    """Raised when a captured tax has an out-of-range rate or an invalid amount."""


class InvalidFulfillmentError(OrderError):
    """Raised when a fulfilment record is missing a carrier/tracking or is malformed."""


class VariantNotFoundError(OrderError):
    """Raised when an ordered SKU has no matching catalog variant."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"unknown variant: {sku}")
        self.sku = sku


class VariantNotPurchasableError(OrderError):
    """Raised when an ordered variant has no price in the checkout channel."""

    def __init__(self, sku: str, channel: str) -> None:
        super().__init__(f"variant {sku} is not purchasable in channel {channel}")
        self.sku = sku
        self.channel = channel


class OutOfStockError(OrderError):
    """Raised when an ordered quantity exceeds the on-hand stock (an oversell)."""

    def __init__(self, sku: str, requested: int, available: int) -> None:
        super().__init__(
            f"insufficient stock for {sku}: requested {requested}, available {available}"
        )
        self.sku = sku
        self.requested = requested
        self.available = available


class OrderNotFoundError(OrderError):
    """Raised when no order matches the owner/number pair."""

    def __init__(self, number: str) -> None:
        super().__init__(f"order not found: {number}")
        self.number = number


class OrderNotCancellableError(OrderError):
    """Raised when an order cannot be cancelled from its current status."""

    def __init__(self, number: str, status: str) -> None:
        super().__init__(f"order {number} cannot be cancelled from status {status!r}")
        self.number = number
        self.status = status


class FulfillmentMethodMismatchError(OrderError):
    """Raised when a fulfilment action does not match the order's delivery method.

    Shipping applies only to a delivery order; the ready-for-pickup / picked-up path applies
    only to a pickup (BOPIS) order. Using the wrong action for the order's method is refused.
    """

    def __init__(self, number: str, *, expected: str) -> None:
        super().__init__(f"order {number} requires a {expected} fulfilment action")
        self.number = number
        self.expected = expected
