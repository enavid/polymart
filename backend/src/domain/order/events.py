"""Domain events published by the order context.

An ``OrderPlaced`` announces that a shopper's cart became a placed, pending order. It
carries the money total and the owner so a subscriber (a confirmation notification, a
fulfilment trigger) has what it needs, but ``to_log`` narrows the logged view to the
non-sensitive fields -- never the amount, never the raw (token-bearing) owner id.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from src.domain.shared.events import DomainEvent


@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    """A shopper's order was placed (pending), by checkout or a staff manual order."""

    name: ClassVar[str] = "order.placed"

    order_number: str
    owner: str
    channel: str
    currency: str
    total: Decimal
    line_count: int

    def to_log(self) -> dict[str, object]:
        # The total (money) and the raw owner (a guest owner embeds a bearer token) are
        # deliberately excluded -- a subscriber reads them off the event, the logs do not.
        return {
            "order_number": self.order_number,
            "channel": self.channel,
            "currency": self.currency,
            "line_count": self.line_count,
        }
