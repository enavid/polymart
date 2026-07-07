"""Domain events published by the payment context.

A ``PaymentCaptured`` announces that money was actually collected for an order (an online
callback captured it, or a wallet payment settled it) -- the moment that drives the order
to ``paid``. It carries the amount and owner for subscribers, but ``to_log`` narrows the
logged view to the non-sensitive fields -- never the amount, never the raw owner id.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from src.domain.shared.events import DomainEvent


@dataclass(frozen=True)
class PaymentCaptured(DomainEvent):
    """A payment was captured (funds collected) for an order."""

    name: ClassVar[str] = "payment.captured"

    payment_reference: str
    order_number: str
    owner: str
    method: str
    amount: Decimal
    currency: str

    def to_log(self) -> dict[str, object]:
        # The amount (money) and the raw owner (a guest owner embeds a bearer token) are
        # deliberately excluded, matching the money-safe logging convention.
        return {
            "payment_reference": self.payment_reference,
            "order_number": self.order_number,
            "method": self.method,
            "currency": self.currency,
        }
