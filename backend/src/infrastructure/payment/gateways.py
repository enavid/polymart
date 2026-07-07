"""Payment gateway adapters -- the concrete implementations of the ``PaymentGateway`` port.

Each payment method is a swappable adapter, so a new one (an online Iranian gateway,
card-to-card) is added here without touching the domain or the use case. This slice ships
the first one: cash on delivery.
"""

from __future__ import annotations

import structlog

from src.application.payment.ports import (
    NextActionType,
    OnlinePaymentGateway,
    PaymentGateway,
    PaymentIntent,
    PaymentStartResult,
    PaymentVerification,
)
from src.domain.payment.value_objects import Money, PaymentMethod
from src.infrastructure.payment.http import HttpTransport

logger = structlog.get_logger(__name__)

# Zarinpal "code 100" is a fresh success; "code 101" means the authority was already
# verified -- both mean the money is captured, so verify treats them identically
# (idempotency at the provider).
_ZARINPAL_SUCCESS_CODES = frozenset({100, 101})


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


class CardToCardGateway(PaymentGateway):
    """Card-to-card: a manual bank transfer the buyer makes and staff verify.

    Like COD, starting a card-to-card payment moves no money and issues no redirect -- the
    buyer transfers to the merchant's per-channel card out of band, reports the transfer
    reference, and staff confirm it (which captures the payment). So ``start`` simply reports
    that there is no automatic next action; the payment stays ``pending`` until staff confirm
    or reject it. The destination card is served separately (owner-scoped), not by the gateway.
    """

    @property
    def method(self) -> PaymentMethod:
        return PaymentMethod.CARD_TO_CARD

    def start(self, intent: PaymentIntent) -> PaymentStartResult:
        logger.info(
            "card_to_card_payment_started",
            payment_reference=intent.reference.value,
            order_number=intent.order_number,
        )
        return PaymentStartResult(next_action=NextActionType.NONE)


class GatewayStartError(Exception):
    """Raised when a gateway refuses to start a payment (no redirect can be issued)."""


class ZarinpalGateway(OnlinePaymentGateway):
    """Zarinpal PSP adapter: request a payment, then verify (capture) it on the callback.

    Zarinpal's flow is request -> redirect to StartPay -> the shopper pays -> Zarinpal
    redirects back to ``callback_url`` with the authority + status -> the server verifies
    (which is the actual capture). Amounts are sent in the smallest unit the merchant is
    configured for (Rial); the exact unit is a merchant/config concern confirmed in prod.
    The adapter depends only on an ``HttpTransport`` port, so it is unit-testable without a
    live network and the HTTP client stays an infrastructure detail.
    """

    def __init__(
        self,
        *,
        transport: HttpTransport,
        merchant_id: str,
        callback_url: str,
        request_url: str,
        verify_url: str,
        start_pay_url: str,
    ) -> None:
        self._transport = transport
        self._merchant_id = merchant_id
        self._callback_url = callback_url
        self._request_url = request_url
        self._verify_url = verify_url
        self._start_pay_url = start_pay_url

    @property
    def method(self) -> PaymentMethod:
        return PaymentMethod.ONLINE

    def start(self, intent: PaymentIntent) -> PaymentStartResult:
        response = self._transport.post_json(
            self._request_url,
            {
                "merchant_id": self._merchant_id,
                "amount": int(intent.amount.amount),
                "callback_url": self._callback_url,
                "description": f"order {intent.order_number}",
            },
        )
        data = response.get("data") or {}
        authority = data.get("authority")
        if data.get("code") not in _ZARINPAL_SUCCESS_CODES or not authority:
            # A request failure has no authority to redirect to; surface it so initiation
            # rolls back rather than sending the shopper to a dead redirect.
            raise GatewayStartError(f"zarinpal request rejected: {response.get('errors')}")
        logger.info(
            "zarinpal_payment_requested",
            payment_reference=intent.reference.value,
            order_number=intent.order_number,
        )
        return PaymentStartResult(
            next_action=NextActionType.REDIRECT,
            redirect_url=f"{self._start_pay_url}/{authority}",
            gateway_reference=authority,
        )

    def verify(self, *, gateway_reference: str, amount: Money) -> PaymentVerification:
        response = self._transport.post_json(
            self._verify_url,
            {
                "merchant_id": self._merchant_id,
                "amount": int(amount.amount),
                "authority": gateway_reference,
            },
        )
        data = response.get("data") or {}
        captured = data.get("code") in _ZARINPAL_SUCCESS_CODES
        ref_id = data.get("ref_id")
        logger.info(
            "zarinpal_payment_verified",
            captured=captured,
            gateway_reference=gateway_reference,
        )
        return PaymentVerification(
            captured=captured,
            provider_reference=str(ref_id) if captured and ref_id is not None else None,
        )


class MockOnlineGateway(OnlinePaymentGateway):
    """A DEBUG-only online gateway that emulates the redirect->callback flow offline.

    There is no real PSP in dev/E2E, so this stands in: ``start`` points the shopper at a
    backend-served mock gateway page (a "Pay"/"Cancel" screen) instead of a real provider,
    and ``verify`` always confirms capture (the shopper's Pay-vs-Cancel choice is carried by
    the callback's status, not by verify). Guarded by ``settings.DEBUG`` at the composition
    root so it can never be wired in production -- exactly like the OTP dev SMS sender.
    """

    def __init__(self, *, mock_page_url: str) -> None:
        self._mock_page_url = mock_page_url

    @property
    def method(self) -> PaymentMethod:
        return PaymentMethod.ONLINE

    def start(self, intent: PaymentIntent) -> PaymentStartResult:
        # The authority is derived from the (already unique) payment reference, so it is
        # deterministic and satisfies the unique gateway_reference constraint.
        authority = f"MOCK-{intent.reference.value}"
        logger.info(
            "mock_online_payment_started",
            payment_reference=intent.reference.value,
            order_number=intent.order_number,
        )
        return PaymentStartResult(
            next_action=NextActionType.REDIRECT,
            redirect_url=f"{self._mock_page_url}?authority={authority}",
            gateway_reference=authority,
        )

    def verify(self, *, gateway_reference: str, amount: Money) -> PaymentVerification:
        return PaymentVerification(
            captured=True, provider_reference=f"MOCK-RID-{gateway_reference}"
        )
