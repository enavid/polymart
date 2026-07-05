"""Payment gateway adapters -- the concrete implementations of the ``PaymentGateway`` port.

Each payment method is a swappable adapter, so a new one (an online Iranian gateway,
card-to-card) is added here without touching the domain or the use case. This slice ships
the first one: cash on delivery.
"""

from __future__ import annotations

import structlog

from src.application.payment.ports import (
    NextActionType,
    PaymentGateway,
    PaymentIntent,
    PaymentStartResult,
)
from src.domain.payment.value_objects import PaymentMethod

logger = structlog.get_logger(__name__)


class CashOnDeliveryGateway(PaymentGateway):
    """Cash on delivery: an offline method that moves no money at checkout.

    Starting a COD payment does nothing external -- the money is collected by the courier
    when the order is handed over (the capture-on-delivery step belongs to the operations
    phase). So ``start`` simply reports that there is no further action for the shopper;
    the payment stays ``pending`` until it is collected out of band.
    """

    @property
    def method(self) -> PaymentMethod:
        return PaymentMethod.COD

    def start(self, intent: PaymentIntent) -> PaymentStartResult:
        # No amount is logged -- only the reference/order and the fact it was started, so
        # the money detail never reaches the logs.
        logger.info(
            "cod_payment_started",
            payment_reference=intent.reference.value,
            order_number=intent.order_number,
        )
        return PaymentStartResult(next_action=NextActionType.NONE)
