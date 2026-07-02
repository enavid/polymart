"""Cart endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result. They hold no
business logic. Domain exceptions are translated to HTTP status codes here.

The cart is always resolved from the request's owner -- the authenticated user, or
an anonymous guest identified by an HttpOnly session cookie -- never from a
client-supplied id, as there is no cart id anywhere in the URL space. That makes
cross-owner access (IDOR) structurally impossible: an owner can only ever reach
their own cart, whether user or guest.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
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
from src.interface.api.guest import OwnerResolution, resolve_owner, set_guest_cookie

logger = structlog.get_logger(__name__)

_CHANNEL_PARAM = OpenApiParameter(
    name="channel", type=str, location=OpenApiParameter.QUERY, required=True
)


def _with_guest_cookie(response: Response, resolution: OwnerResolution) -> Response:
    """Attach the guest session cookie to the response when a new guest was minted.

    A no-op for authenticated requests and for guests who already carry a cookie, so
    only a guest's first cart write ever sets it -- never a read, never a user.
    """
    if resolution.set_cookie is not None:
        set_guest_cookie(response, resolution.set_cookie)
    return response


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
    """Read the current owner's cart for a channel (user or guest)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        parameters=[_CHANNEL_PARAM],
        responses={200: PricedCartSerializer, 400: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = CartChannelQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        # A read never mints a guest cookie: a cookieless visitor simply reads empty.
        resolution = resolve_owner(request, mint=False)
        query = GetCartQuery(owner=resolution.owner, channel=params.validated_data["channel"])
        try:
            priced = build_get_cart().execute(query)
        except CartError as exc:
            # An unknown/blank channel surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return _with_guest_cookie(Response(_cart_payload(priced)), resolution)


class CartItemsView(APIView):
    """Add a variant to the cart (or increase its quantity if already present)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        request=AddCartItemSerializer,
        responses={
            200: PricedCartSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # The first write is where a guest's session identity is minted (and its cookie
        # set below), so their cart persists across subsequent requests.
        resolution = resolve_owner(request, mint=True)
        command = AddCartItemCommand(
            owner=resolution.owner,
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
        return _with_guest_cookie(Response(_cart_payload(priced)), resolution)


class CartItemDetailView(APIView):
    """Update or remove a single line of the current owner's cart (user or guest)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        request=UpdateCartItemSerializer,
        responses={
            200: PricedCartSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, sku: str) -> Response:
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Updating presupposes an existing cart, so a cookieless guest resolves to a
        # throwaway owner with no cart -> 404 (mint=False: no cookie for that).
        resolution = resolve_owner(request, mint=False)
        command = UpdateCartItemCommand(
            owner=resolution.owner,
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
        return _with_guest_cookie(Response(_cart_payload(priced)), resolution)

    @extend_schema(
        parameters=[_CHANNEL_PARAM],
        responses={
            200: PricedCartSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def delete(self, request: Request, sku: str) -> Response:
        params = CartChannelQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        resolution = resolve_owner(request, mint=False)
        command = RemoveCartItemCommand(
            owner=resolution.owner, channel=params.validated_data["channel"], sku=sku
        )
        try:
            priced = build_remove_cart_item().execute(command)
        except CartLineNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CartError as exc:
            # A malformed/unknown channel surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return _with_guest_cookie(Response(_cart_payload(priced)), resolution)
