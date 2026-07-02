"""Order endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result -- no business
logic. Domain exceptions are translated to HTTP status codes here.

Every route resolves the order from the authenticated user (``request.user``); there is
no owner id in the request body, and reads are owner-scoped in the repository, so one
shopper can never place, read, or cancel another's order (IDOR is structurally
impossible). Order numbers are opaque and unguessable, so appearing in a URL leaks
nothing.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.order.use_cases import (
    DEFAULT_PAGE_LIMIT,
    CancelMyOrderCommand,
    InvalidOrderPageError,
    ListMyOrdersQuery,
    PlaceOrderCommand,
)
from src.domain.order.entities import Order
from src.domain.order.exceptions import (
    EmptyCartError,
    OrderError,
    OrderNotCancellableError,
    OrderNotFoundError,
    OutOfStockError,
    UnknownChannelError,
    UnknownShippingAddressError,
    VariantNotFoundError,
    VariantNotPurchasableError,
)
from src.interface.api.common import ErrorSerializer
from src.interface.api.order.container import (
    build_cancel_my_order,
    build_get_my_order,
    build_list_my_orders,
    build_place_order,
)
from src.interface.api.order.serializers import (
    OrderListQuerySerializer,
    OrderPageSerializer,
    OrderSerializer,
    PlaceOrderSerializer,
)

logger = structlog.get_logger(__name__)


def _owner(request: Request) -> str:
    """The authenticated user's stable id -- the order's owner (never the PII username)."""
    return str(request.user.pk)


def _order_payload(order: Order) -> dict[str, object]:
    """Project an order to the response body (money as exact strings)."""
    return {
        "number": order.number.value,
        "channel": order.channel.value,
        "currency": order.currency,
        "status": order.status.value,
        "total": str(order.total.amount),
        "placed_at": order.placed_at,
        "items": [
            {
                "sku": line.sku.value,
                "quantity": line.quantity.value,
                "unit_price": str(line.unit_price.amount),
                "line_total": str(line.line_total.amount),
            }
            for line in order.lines
        ],
        "shipping_address": {
            "recipient_name": order.shipping_address.recipient_name,
            "phone_number": order.shipping_address.phone_number,
            "province": order.shipping_address.province,
            "city": order.shipping_address.city,
            "postal_code": order.shipping_address.postal_code,
            "line1": order.shipping_address.line1,
            "line2": order.shipping_address.line2,
        },
    }


class OrderCollectionView(APIView):
    """List the authenticated shopper's orders, or place a new one (checkout)."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        operation_id="orders_list",
        parameters=[
            OpenApiParameter(name="limit", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="offset", type=int, location=OpenApiParameter.QUERY),
        ],
        responses={200: OrderPageSerializer, 400: ErrorSerializer, 401: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = OrderListQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        limit = params.validated_data.get("limit", DEFAULT_PAGE_LIMIT)
        offset = params.validated_data.get("offset", 0)
        try:
            page = build_list_my_orders().execute(
                ListMyOrdersQuery(owner=_owner(request), limit=limit, offset=offset)
            )
        except InvalidOrderPageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "count": page.total,
                "limit": limit,
                "offset": offset,
                "results": [_order_payload(order) for order in page.items],
            }
        )

    @extend_schema(
        operation_id="orders_place",
        request=PlaceOrderSerializer,
        responses={
            201: OrderSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = PlaceOrderCommand(
            owner=_owner(request),
            channel=serializer.validated_data["channel"],
            address_id=serializer.validated_data["address_id"],
        )
        try:
            order = build_place_order().execute(command)
        except (UnknownChannelError, UnknownShippingAddressError) as exc:
            # A well-formed request-body reference (channel or saved address) that does
            # not resolve for this shopper. A not-owned address resolves to the same
            # error as a nonexistent one, so checkout never reveals whether another
            # shopper's address id exists.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except VariantNotFoundError as exc:  # pragma: no cover - defensive
            # Unreachable in practice: the price check precedes the stock deduction, and
            # a price row exists only while its variant does, so a priced line always
            # resolves to a variant. Kept as a precise mapping if that ever changes.
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (EmptyCartError, OutOfStockError, VariantNotPurchasableError) as exc:
            # A conflict with the current cart/stock state (empty cart, oversell, a line
            # that lost its price) -- the request was well-formed but cannot be honoured.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderError as exc:  # pragma: no cover - defensive catch-all
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_order_payload(order), status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """Read one of the authenticated shopper's orders by number."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        operation_id="orders_retrieve",
        responses={200: OrderSerializer, 401: ErrorSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, number: str) -> Response:
        try:
            order = build_get_my_order().execute(owner=_owner(request), number=number)
        except OrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except OrderError as exc:
            # A malformed order number can never match -- surface as 404, not a 400, so
            # the shape of a valid number is not probed.
            logger.debug("order_lookup_rejected", detail=str(exc))
            return Response({"detail": "order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_order_payload(order))


class OrderCancelView(APIView):
    """Cancel one of the authenticated shopper's still-pending orders."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        operation_id="orders_cancel",
        request=None,
        responses={
            200: OrderSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, number: str) -> Response:
        try:
            order = build_cancel_my_order().execute(
                CancelMyOrderCommand(owner=_owner(request), number=number)
            )
        except OrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except OrderNotCancellableError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderError:
            return Response({"detail": "order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_order_payload(order))
