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

from src.application.payment.use_cases import InitiatePaymentCommand, PaymentResult
from src.domain.payment.entities import Payment
from src.domain.payment.exceptions import (
    InvalidPaymentMethodError,
    OrderNotPayableError,
    PaymentAlreadyExistsError,
    PaymentError,
    PaymentNotFoundError,
    PaymentOrderNotFoundError,
    UnsupportedPaymentMethodError,
)
from src.infrastructure.payment.tasks import capture_online_payment
from src.interface.api.common import ErrorSerializer
from src.interface.api.guest import resolve_owner
from src.interface.api.payment.container import (
    build_get_my_payment,
    build_get_payment_by_gateway_reference,
    build_get_payment_for_order,
    build_initiate_payment,
)
from src.interface.api.payment.serializers import (
    InitiatePaymentSerializer,
    PaymentInitiationSerializer,
    PaymentSerializer,
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
        command = InitiatePaymentCommand(
            owner=_owner(request),
            order_number=data["order_number"],
            method=data["method"],
        )
        try:
            result = build_initiate_payment().execute(command)
        except PaymentOrderNotFoundError as exc:
            # Unknown, or another shopper's -- indistinguishable, so payment never reveals
            # whether another shopper's order exists.
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (InvalidPaymentMethodError, UnsupportedPaymentMethodError) as exc:
            # A method that is not recognised, or recognised but has no gateway yet.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (OrderNotPayableError, PaymentAlreadyExistsError) as exc:
            # A conflict with the order's current state (already paid/cancelled) or an
            # existing active payment -- the request was well-formed but cannot be honoured.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError as exc:  # pragma: no cover - defensive catch-all
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_initiation_payload(result), status=status.HTTP_201_CREATED)


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
