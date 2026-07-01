"""Cart endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result. They hold no
business logic. Domain exceptions are translated to HTTP status codes here.

The cart is always resolved from the authenticated user (``request.user``), never
from a client-supplied id -- there is no cart id anywhere in the URL space. That
makes cross-user access (IDOR) structurally impossible: a shopper can only ever
reach their own cart.
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

from src.application.cart.use_cases import (
    AddCartItemCommand,
    GetCartQuery,
    RemoveCartItemCommand,
    UpdateCartItemCommand,
)
from src.domain.cart.exceptions import (
    CartError,
    CartLineNotFoundError,
    VariantNotFoundError,
)
from src.domain.cart.services import PricedCart, PricedLine
from src.domain.cart.value_objects import Money
from src.interface.api.cart.container import (
    build_add_cart_item,
    build_get_cart,
    build_remove_cart_item,
    build_update_cart_item,
)
from src.interface.api.cart.serializers import (
    AddCartItemSerializer,
    CartChannelQuerySerializer,
    PricedCartSerializer,
    UpdateCartItemSerializer,
)
from src.interface.api.common import ErrorSerializer

logger = structlog.get_logger(__name__)

_CHANNEL_PARAM = OpenApiParameter(
    name="channel", type=str, location=OpenApiParameter.QUERY, required=True
)


def _owner(request: Request) -> str:
    """The authenticated user's stable id -- the cart's owner.

    The primary key, never the username (the phone number is PII and must never
    reach the logs). ``IsAuthenticated`` guarantees a real user here.
    """
    return str(request.user.pk)


def _money_str(money: Money | None) -> str | None:
    """Render a ``Money`` amount as an exact string, or ``None`` when absent."""
    if money is None:
        return None
    return str(money.amount)


def _line_payload(line: PricedLine) -> dict[str, object]:
    return {
        "sku": line.sku.value,
        "quantity": line.quantity.value,
        "unit_price": _money_str(line.unit_price),
        "line_total": _money_str(line.line_total),
        "available": line.available,
    }


def _cart_payload(priced: PricedCart) -> dict[str, object]:
    """Project a priced cart to the response body (money as exact strings)."""
    return {
        "channel": priced.channel,
        "currency": priced.currency,
        "items": [_line_payload(line) for line in priced.lines],
        "total": str(priced.total.amount),
    }


class CartView(APIView):
    """Read the authenticated shopper's cart for a channel."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        parameters=[_CHANNEL_PARAM],
        responses={200: PricedCartSerializer, 400: ErrorSerializer, 401: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = CartChannelQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        query = GetCartQuery(owner=_owner(request), channel=params.validated_data["channel"])
        try:
            priced = build_get_cart().execute(query)
        except CartError as exc:
            # An unknown/blank channel surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_cart_payload(priced))


class CartItemsView(APIView):
    """Add a variant to the cart (or increase its quantity if already present)."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        request=AddCartItemSerializer,
        responses={
            200: PricedCartSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = AddCartItemCommand(
            owner=_owner(request),
            channel=data["channel"],
            sku=data["sku"],
            quantity=data["quantity"],
        )
        try:
            priced = build_add_cart_item().execute(command)
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CartError as exc:
            # Malformed sku/quantity/channel, unknown channel, or an unpurchasable variant.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_cart_payload(priced))


class CartItemDetailView(APIView):
    """Update or remove a single line of the authenticated shopper's cart."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        request=UpdateCartItemSerializer,
        responses={
            200: PricedCartSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, sku: str) -> Response:
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = UpdateCartItemCommand(
            owner=_owner(request),
            channel=data["channel"],
            sku=sku,
            quantity=data["quantity"],
        )
        try:
            priced = build_update_cart_item().execute(command)
        except CartLineNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CartError as exc:
            # Malformed quantity/channel or an unknown channel.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_cart_payload(priced))

    @extend_schema(
        parameters=[_CHANNEL_PARAM],
        responses={
            200: PricedCartSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def delete(self, request: Request, sku: str) -> Response:
        params = CartChannelQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        command = RemoveCartItemCommand(
            owner=_owner(request), channel=params.validated_data["channel"], sku=sku
        )
        try:
            priced = build_remove_cart_item().execute(command)
        except CartLineNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CartError as exc:
            # A malformed/unknown channel surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_cart_payload(priced))
