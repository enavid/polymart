"""The Order aggregate: a placed, immutable-priced record of a purchase.

Unlike a cart (a mutable, dynamically priced list of intentions), an order *captures*
prices at placement time: each line stores the unit price and line total that were in
force, so a later catalog price change never rewrites history. The shipping address is
captured the same way -- copied from the owner's address book at placement, not
referenced by id, so a later edit or deletion of that saved address never rewrites a
placed order's history either. The aggregate owns two invariants -- every line is in
the order's currency, and the stated total equals the sum of the line totals -- and the
lifecycle state machine that governs which status changes are legal.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from src.domain.order.exceptions import (
    EmptyOrderError,
    IllegalOrderTransitionError,
    OrderCurrencyMismatchError,
    OrderTotalMismatchError,
)
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    ShippingAddress,
    Sku,
)

# The order state machine: which statuses each status may move to. A terminal state
# maps to an empty set. Kept as data (not scattered if/else) so the legal lifecycle is
# declared in one readable place.
_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.PAID, OrderStatus.CANCELLED}),
    OrderStatus.PAID: frozenset({OrderStatus.FULFILLED, OrderStatus.CANCELLED}),
    OrderStatus.FULFILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class OrderLine:
    """One captured line of an order: what was bought, how many, at what price.

    ``line_total`` must equal ``unit_price`` scaled by ``quantity`` -- it is stored
    (not merely derived) so the persisted row is self-describing, but the invariant is
    enforced here so a mismatched snapshot can never exist.
    """

    sku: Sku
    quantity: OrderQuantity
    unit_price: Money
    line_total: Money

    def __post_init__(self) -> None:
        expected = self.unit_price.times(self.quantity)
        if self.line_total.currency != self.unit_price.currency:
            raise OrderCurrencyMismatchError(
                f"line {self.sku.value}: total {self.line_total.currency!r} "
                f"!= unit {self.unit_price.currency!r}"
            )
        if self.line_total.amount != expected.amount:
            raise OrderTotalMismatchError(
                f"line {self.sku.value}: total {self.line_total.amount} "
                f"!= unit x qty {expected.amount}"
            )


@dataclass(frozen=True)
class Order:
    """A placed order: an owner's captured purchase in one channel.

    Identity is the public ``number`` (and the database ``id`` once persisted). The
    owner is the stable user id -- an order is always resolved from the authenticated
    user, never from a client-supplied id, so cross-user access is impossible.
    """

    number: OrderNumber
    owner: str
    channel: ChannelRef
    currency: str
    lines: tuple[OrderLine, ...]
    total: Money
    status: OrderStatus
    placed_at: datetime
    shipping_address: ShippingAddress
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.lines:
            raise EmptyOrderError("an order must have at least one line")
        summed = Money.zero(self.currency)
        for line in self.lines:
            if line.line_total.currency != self.currency:
                raise OrderCurrencyMismatchError(
                    f"line {line.sku.value} currency {line.line_total.currency!r} "
                    f"!= order currency {self.currency!r}"
                )
            summed = summed.add(line.line_total)
        if self.total.currency != self.currency or self.total.amount != summed.amount:
            raise OrderTotalMismatchError(
                f"order total {self.total.amount} {self.total.currency} "
                f"!= sum of lines {summed.amount} {summed.currency}"
            )

    def transition_to(self, target: OrderStatus) -> Order:
        """Return a copy of the order in ``target`` status, or raise if illegal.

        The aggregate is immutable, so a transition yields a new instance rather than
        mutating in place; the state machine table is the single source of truth for
        what is allowed.
        """
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise IllegalOrderTransitionError(self.status.value, target.value)
        return replace(self, status=target)

    def cancel(self) -> Order:
        """Return a cancelled copy of the order (only legal from a non-terminal state)."""
        return self.transition_to(OrderStatus.CANCELLED)
