"""Payment endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result -- no business logic.
Domain exceptions are translated to HTTP status codes here.

Every route resolves the payment's owner from the request -- the authenticated user, or an
anonymous guest identified by their HttpOnly session cookie -- never from a client-supplied
id: there is no owner id in the request, the order/payment references are opaque, and reads
are owner-scoped in the repository, so one shopper can never initiate, read, or pay against
another's order (IDOR is structurally impossible for guests and users alike).
"""

from __future__ import annotations

from html import escape
from typing import ClassVar
from urllib.parse import quote

import structlog
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.payment.use_cases import (
    ConfirmCardToCardPaymentCommand,
    InitiatePaymentCommand,
    PaymentResult,
    PayWithWalletCommand,
    RefundPaymentCommand,
    RejectCardToCardPaymentCommand,
    SubmitCardToCardReferenceCommand,
)
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import (
    CardToCardNotConfiguredError,
    InsufficientWalletBalanceError,
    InvalidPaymentMethodError,
    NotACardToCardPaymentError,
    OrderNotPayableError,
    PaymentAlreadyExistsError,
    PaymentError,
    PaymentNotAwaitingTransferError,
    PaymentNotConfirmableError,
    PaymentNotFoundError,
    PaymentNotRefundableError,
    PaymentOrderNotFoundError,
    TransferReferenceAlreadySubmittedError,
    UnsupportedPaymentMethodError,
    WalletOwnerRequiredError,
    WalletPaymentRequiresUserError,
)
from src.domain.payment.value_objects import PaymentMethod
from src.infrastructure.payment.tasks import capture_online_payment
from src.interface.api.access.permissions import OrderManagePermission
from src.interface.api.common import ErrorSerializer
from src.interface.api.guest import resolve_owner, user_owner
from src.interface.api.payment.container import (
    build_confirm_card_to_card_payment,
    build_get_card_to_card_instructions,
    build_get_my_payment,
    build_get_payment_by_gateway_reference,
    build_get_payment_for_order,
    build_initiate_payment,
    build_pay_with_wallet,
    build_refund_payment,
    build_reject_card_to_card_payment,
    build_submit_card_to_card_reference,
)
from src.interface.api.payment.serializers import (
    CardToCardInstructionsSerializer,
    InitiatePaymentSerializer,
    PaymentInitiationSerializer,
    PaymentSerializer,
    SubmitTransferReferenceSerializer,
)

logger = structlog.get_logger(__name__)


def _owner(request: Request) -> str:
    """The request's payment owner -- ``u:<pk>`` for a user, ``g:<token>`` for a guest.

    Payments are never minted a new guest cookie: a guest reaching payment already holds
    one (they built a cart and placed an order with it), and a cookieless request resolves
    to a throwaway owner that owns no order (so initiating resolves to "order not found").
    """
    return resolve_owner(request, mint=False).owner


def _payment_payload(payment: Payment) -> dict[str, object]:
    """Project a payment to the response body (amount as an exact string)."""
    return {
        "reference": payment.reference.value,
        "order_number": payment.order_ref.value,
        "method": payment.method.value,
        "amount": str(payment.amount.amount),
        "currency": payment.amount.currency,
        "status": payment.status.value,
        "created_at": payment.created_at,
        "transfer_reference": payment.transfer_reference,
    }


def _initiation_payload(result: PaymentResult) -> dict[str, object]:
    """Project an initiation result: the payment plus what the shopper must do next."""
    return {
        **_payment_payload(result.payment),
        "next_action": result.next_action.value,
        "redirect_url": result.redirect_url,
    }


class PaymentCollectionView(APIView):
    """Initiate a payment for one of the current shopper's own orders -- user or guest."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="payments_initiate",
        request=InitiatePaymentSerializer,
        responses={
            201: PaymentInitiationSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = InitiatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = _owner(request)
        try:
            result = self._settle(owner, data["order_number"], data["method"])
        except PaymentOrderNotFoundError as exc:
            # Unknown, or another shopper's -- indistinguishable, so payment never reveals
            # whether another shopper's order exists.
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (
            InvalidPaymentMethodError,
            UnsupportedPaymentMethodError,
        ) as exc:  # pragma: no cover - safety net: every current method has an adapter and the
            # serializer rejects unknown ones, so this fires only if a future method is added to
            # the enum without registering a gateway.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (
            OrderNotPayableError,
            PaymentAlreadyExistsError,
            WalletPaymentRequiresUserError,
            InsufficientWalletBalanceError,
        ) as exc:
            # A conflict with the order's current state (already paid/cancelled), an existing
            # active payment, or a wallet that cannot pay (a guest, or an uncovered balance)
            # -- the request was well-formed but cannot be honoured.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError as exc:  # pragma: no cover - defensive catch-all
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_initiation_payload(result), status=status.HTTP_201_CREATED)

    @staticmethod
    def _settle(owner: str, order_number: str, method: str) -> PaymentResult:
        """Route to the wallet settlement or the gateway-backed initiation by method.

        Wallet payment settles synchronously and internally (its own use case); every other
        method is started through the gateway registry. Both return a ``PaymentResult`` so the
        response shape is identical.
        """
        if method == PaymentMethod.WALLET.value:
            return build_pay_with_wallet().execute(
                PayWithWalletCommand(owner=owner, order_number=order_number)
            )
        return build_initiate_payment().execute(
            InitiatePaymentCommand(owner=owner, order_number=order_number, method=method)
        )


class PaymentForOrderView(APIView):
    """Read the payment for one of the current shopper's own orders (user or guest)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="payments_for_order",
        responses={200: PaymentSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, number: str) -> Response:
        try:
            payment = build_get_payment_for_order().execute(
                owner=_owner(request), order_number=number
            )
        except PaymentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except PaymentError:
            # A malformed order number can never match -- surface as 404, not a 400.
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payment_payload(payment))


class PaymentDetailView(APIView):
    """Read one of the current shopper's payments by reference (user or guest)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="payments_retrieve",
        responses={200: PaymentSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, reference: str) -> Response:
        try:
            payment = build_get_my_payment().execute(owner=_owner(request), reference=reference)
        except PaymentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except PaymentError:
            # A malformed reference can never match -- surface as 404, not a 400, so the
            # shape of a valid reference is not probed.
            logger.debug("payment_lookup_rejected")
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payment_payload(payment))


class PaymentRefundView(APIView):
    """Refund a captured payment to the shopper's wallet -- staff only.

    A privileged, platform-global staff action (gated by ``manage_orders``): it addresses a
    payment by its public reference (not owner-scoped -- staff act on any shopper's payment)
    and returns the full captured amount as internal store credit. Idempotent: refunding an
    already-refunded payment returns it unchanged without crediting again.
    """

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="payments_refund",
        request=None,
        responses={
            200: PaymentSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, reference: str) -> Response:
        command = RefundPaymentCommand(reference=reference, actor=user_owner(request.user.pk))
        try:
            payment = build_refund_payment().execute(command)
        except PaymentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (PaymentNotRefundableError, WalletOwnerRequiredError) as exc:
            # A conflict with the payment's current state (not captured) or an owner that
            # cannot hold a wallet (a guest) -- well-formed but not honourable.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError:
            # A malformed reference can never match -- surface as 404, not a 400, so the
            # shape of a valid reference is not probed.
            logger.debug("payment_refund_rejected")
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payment_payload(payment))


class CardToCardInstructionsView(APIView):
    """Read the destination card a buyer must transfer to for their card-to-card order.

    Owner-scoped (user or guest): resolves the caller's own order and returns its channel's
    receiving card, so another shopper's order is indistinguishable from a nonexistent one.
    """

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="payments_card_to_card_instructions",
        responses={
            200: CardToCardInstructionsSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def get(self, request: Request, number: str) -> Response:
        try:
            destination = build_get_card_to_card_instructions().execute(
                owner=_owner(request), order_number=number
            )
        except PaymentOrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CardToCardNotConfiguredError as exc:
            # The channel has no receiving card set up -- a server-side configuration gap.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError:
            return Response({"detail": "order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {"card_number": destination.card_number, "card_holder": destination.card_holder}
        )


class TransferReferenceView(APIView):
    """Submit the buyer's card-to-card transfer reference for their own pending order."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="payments_submit_transfer_reference",
        request=SubmitTransferReferenceSerializer,
        responses={
            200: PaymentSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, number: str) -> Response:
        serializer = SubmitTransferReferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SubmitCardToCardReferenceCommand(
            owner=_owner(request),
            order_number=number,
            transfer_reference=serializer.validated_data["transfer_reference"],
        )
        try:
            payment = build_submit_card_to_card_reference().execute(command)
        except PaymentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (
            NotACardToCardPaymentError,
            PaymentNotAwaitingTransferError,
            TransferReferenceAlreadySubmittedError,
        ) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError:
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payment_payload(payment))


class CardToCardConfirmView(APIView):
    """Confirm a buyer's card-to-card transfer, capturing the payment -- staff only.

    A privileged, platform-global staff action (gated by ``manage_orders``): staff verify the
    transfer the buyer reported, then confirm it, which captures the payment and marks the
    order paid. Idempotent: confirming an already-captured payment returns it unchanged.
    """

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="payments_confirm_card_to_card",
        request=None,
        responses={
            200: PaymentSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, reference: str) -> Response:
        command = ConfirmCardToCardPaymentCommand(
            reference=reference, actor=user_owner(request.user.pk)
        )
        try:
            payment = build_confirm_card_to_card_payment().execute(command)
        except PaymentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (NotACardToCardPaymentError, PaymentNotConfirmableError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError:
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payment_payload(payment))


class CardToCardRejectView(APIView):
    """Reject a buyer's card-to-card transfer, failing the payment -- staff only.

    A privileged, platform-global staff action (gated by ``manage_orders``): when staff cannot
    verify the reported transfer, they reject it, which fails the payment and frees the order
    for a fresh attempt. Idempotent: rejecting an already-failed payment returns it unchanged.
    """

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="payments_reject_card_to_card",
        request=None,
        responses={
            200: PaymentSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, reference: str) -> Response:
        command = RejectCardToCardPaymentCommand(
            reference=reference, actor=user_owner(request.user.pk)
        )
        try:
            payment = build_reject_card_to_card_payment().execute(command)
        except PaymentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (NotACardToCardPaymentError, PaymentNotConfirmableError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError:
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payment_payload(payment))


def _callback_param(request: Request, *names: str) -> str | None:
    """Read the first present query param among ``names`` (gateways vary on casing)."""
    for name in names:
        value = request.query_params.get(name)
        if value:
            return value
    return None


class PaymentCallbackView(APIView):
    """The online gateway callback (the "webhook"): settle a payment and return the shopper.

    The gateway redirects the shopper's browser here with the authority + a status. Settlement
    is handed to an idempotent Celery task (so a duplicate callback never double-captures), and
    the browser is redirected to the storefront order page to see the result. Not owner-scoped:
    the callback carries only the unguessable authority (the server re-verifies with the gateway
    inside the task, so a spoofed "success" cannot capture without the gateway's confirmation).
    """

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="payments_callback",
        responses={302: None, 400: ErrorSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request) -> HttpResponse:
        authority = _callback_param(request, "Authority", "authority")
        gateway_status = _callback_param(request, "Status", "status")
        if authority is None:
            return Response({"detail": "missing authority"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment = build_get_payment_by_gateway_reference().execute(gateway_reference=authority)
        except PaymentNotFoundError:
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)
        except PaymentError:  # pragma: no cover - defensive
            return Response({"detail": "payment not found"}, status=status.HTTP_404_NOT_FOUND)

        # Settle out of band (idempotent). Eager in tests, so the result is ready immediately.
        capture_online_payment.delay(authority, succeeded=gateway_status == "OK")

        target = f"{settings.PAYMENT_RESULT_URL}/{quote(payment.order_ref.value)}"
        return HttpResponseRedirect(target)


class MockGatewayView(APIView):
    """A DEBUG/mock-only stand-in for the gateway's hosted payment page.

    Renders a minimal "Pay"/"Cancel" screen that links back to the callback with the
    authority and an OK/NOK status -- letting the full redirect->callback flow run offline in
    dev and E2E. Refuses to serve unless the mock online gateway is the one wired
    (``PAYMENT_ONLINE_MOCK``), so it is inert in production.
    """

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(operation_id="payments_mock_gateway", responses={200: None, 404: None})
    def get(self, request: Request) -> HttpResponse:
        if not settings.PAYMENT_ONLINE_MOCK:
            return HttpResponse(status=status.HTTP_404_NOT_FOUND)
        authority = request.query_params.get("authority", "")
        callback = settings.PAYMENT_CALLBACK_URL
        safe_authority = quote(authority)
        pay = f"{callback}?Authority={safe_authority}&Status=OK"
        cancel = f"{callback}?Authority={safe_authority}&Status=NOK"
        # authority is echoed only inside an href we build with quote(); escape() guards the
        # visible text too so the mock page cannot be turned into an XSS vector.
        body = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<title>Mock gateway</title></head><body>"
            "<h1>Mock payment gateway</h1>"
            f"<p>Authority: {escape(authority)}</p>"
            f"<a id='mock_pay' href='{pay}'>Pay</a> "
            f"<a id='mock_cancel' href='{cancel}'>Cancel</a>"
            "</body></html>"
        )
        return HttpResponse(body, content_type="text/html")
