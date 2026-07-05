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

from typing import ClassVar

import structlog
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
from src.interface.api.common import ErrorSerializer
from src.interface.api.guest import resolve_owner
from src.interface.api.payment.container import (
    build_get_my_payment,
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
