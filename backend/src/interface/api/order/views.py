"""Order endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result -- no business
logic. Domain exceptions are translated to HTTP status codes here.

Every route resolves the order's owner from the request -- the authenticated user, or an
anonymous guest identified by their HttpOnly session cookie -- never from a
client-supplied id: there is no owner id in the request body, and reads are owner-scoped
in the repository, so one shopper can never place, read, or cancel another's order (IDOR
is structurally impossible for guests and users alike). Order numbers are opaque and
unguessable, so appearing in a URL leaks nothing.
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

from src.application.order.ports import InlineShippingAddress
from src.application.order.use_cases import (
    DEFAULT_PAGE_LIMIT,
    CancelMyOrderCommand,
    CreateManualOrderCommand,
    FulfillmentActionCommand,
    InvalidOrderPageError,
    ListMyOrdersQuery,
    ManualOrderItem,
    PlaceOrderCommand,
    ShipOrderCommand,
)
from src.domain.order.entities import Order
from src.domain.order.exceptions import (
    DuplicateOrderLineError,
    EmptyCartError,
    EmptyOrderError,
    FulfillmentMethodMismatchError,
    IllegalOrderTransitionError,
    OrderError,
    OrderNotCancellableError,
    OrderNotFoundError,
    OutOfStockError,
    UnknownChannelError,
    UnknownShippingAddressError,
    UnknownShippingMethodError,
    VariantNotFoundError,
    VariantNotPurchasableError,
)
from src.interface.api.access.permissions import OrderManagePermission
from src.interface.api.common import ErrorSerializer
from src.interface.api.guest import resolve_owner, user_owner
from src.interface.api.order.container import (
    build_cancel_my_order,
    build_confirm_order_pickup,
    build_create_manual_order,
    build_get_my_order,
    build_get_order_for_invoice,
    build_list_my_orders,
    build_mark_order_ready_for_pickup,
    build_place_order,
    build_ship_order,
)
from src.interface.api.order.serializers import (
    ManualOrderSerializer,
    OrderListQuerySerializer,
    OrderPageSerializer,
    OrderSerializer,
    PlaceOrderSerializer,
    PreInvoiceSerializer,
    ShipOrderSerializer,
)

logger = structlog.get_logger(__name__)


def _owner(request: Request) -> str:
    """The request's order owner -- ``u:<pk>`` for a user, ``g:<token>`` for a guest.

    Orders are never minted a new guest cookie: a guest reaching checkout already holds
    one from building their cart, and a cookieless request resolves to a throwaway owner
    that owns no cart/order (so it reads empty and cannot place -- empty cart -> 409).
    """
    return resolve_owner(request, mint=False).owner


def _inline_shipping(data: dict[str, object]) -> InlineShippingAddress | None:
    """Build the inline shipping address from validated data, if a guest supplied one."""
    raw = data.get("shipping_address")
    if raw is None:
        return None
    address = dict(raw)  # type: ignore[call-overload]
    return InlineShippingAddress(
        recipient_name=address["recipient_name"],
        phone_number=address["phone_number"],
        province=address["province"],
        city=address["city"],
        postal_code=address["postal_code"],
        line1=address["line1"],
        line2=address.get("line2") or None,
    )


def _order_payload(order: Order) -> dict[str, object]:
    """Project an order to the response body (money as exact strings)."""
    shipping = order.shipping
    tax = order.tax
    address = order.shipping_address
    fulfillment = order.fulfillment
    return {
        "number": order.number.value,
        "channel": order.channel.value,
        "currency": order.currency,
        "status": order.status.value,
        "subtotal": str(order.items_subtotal.amount),
        "shipping_cost": str(order.shipping_cost.amount),
        "shipping_method": shipping.method_code if shipping is not None else None,
        "shipping_method_name": shipping.method_name if shipping is not None else None,
        # ``tax`` is the captured tax amount and ``tax_rate`` the percentage; both are ``null``
        # for an order in an untaxed channel (and orders that predate tax).
        "tax": str(tax.amount.amount) if tax is not None else None,
        "tax_rate": str(tax.rate) if tax is not None else None,
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
        # A pickup (BOPIS) order captures no address; ``is_pickup`` drives which fulfilment
        # controls the client shows.
        "is_pickup": shipping.is_pickup if shipping is not None else False,
        "shipping_address": (
            {
                "recipient_name": address.recipient_name,
                "phone_number": address.phone_number,
                "province": address.province,
                "city": address.city,
                "postal_code": address.postal_code,
                "line1": address.line1,
                "line2": address.line2,
            }
            if address is not None
            else None
        ),
        "fulfillment": (
            {
                "carrier": fulfillment.carrier,
                "tracking_number": fulfillment.tracking_number,
                "tracking_url": fulfillment.tracking_url,
            }
            if fulfillment is not None
            else None
        ),
    }


def _pre_invoice_payload(order: Order) -> dict[str, object]:
    """Project an order to its pre-invoice (proforma) body.

    The full order plus a document marker: ``tax`` comes from the captured order (``null`` when
    the channel is untaxed), and the grand total equals the order total (which already includes
    the tax).
    """
    return {
        **_order_payload(order),
        "document_type": "pre_invoice",
        "grand_total": str(order.total.amount),
    }


class ManualOrderView(APIView):
    """Create a manual order (a pre-invoice) from staff-supplied lines -- staff only."""

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="orders_manual_create",
        request=ManualOrderSerializer,
        responses={
            201: OrderSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ManualOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateManualOrderCommand(
            actor=user_owner(request.user.pk),
            channel=data["channel"],
            items=tuple(
                ManualOrderItem(sku=item["sku"], quantity=item["quantity"])
                for item in data["items"]
            ),
            shipping_address=_inline_shipping(data),  # type: ignore[arg-type]
        )
        try:
            order = build_create_manual_order().execute(command)
        except UnknownChannelError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (DuplicateOrderLineError, EmptyOrderError) as exc:  # pragma: no cover - defensive
            # The serializer already rejects an empty or duplicated line list with a 400;
            # this maps the domain's own invariant as a safety net if that ever changes.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except VariantNotFoundError as exc:  # pragma: no cover - defensive
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (OutOfStockError, VariantNotPurchasableError) as exc:
            # A well-formed request that conflicts with the current stock/price state.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderError as exc:  # pragma: no cover - defensive catch-all
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_order_payload(order), status=status.HTTP_201_CREATED)


class PreInvoiceView(APIView):
    """Read any order's pre-invoice (proforma) for printing -- staff only."""

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="orders_pre_invoice",
        responses={200: PreInvoiceSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, number: str) -> Response:
        try:
            order = build_get_order_for_invoice().execute(number=number)
        except OrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except OrderError:
            # A malformed number can never match -- surface as 404, not a 400.
            return Response({"detail": "order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_pre_invoice_payload(order))


class ShipOrderView(APIView):
    """Ship a paid delivery order: capture carrier + tracking, move to fulfilled -- staff only."""

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="orders_ship",
        request=ShipOrderSerializer,
        responses={
            200: OrderSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, number: str) -> Response:
        serializer = ShipOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = ShipOrderCommand(
            number=number,
            carrier=data["carrier"],
            tracking_number=data["tracking_number"],
            tracking_url=data.get("tracking_url") or None,
        )
        try:
            order = build_ship_order().execute(command, actor=user_owner(request.user.pk))
        except OrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (FulfillmentMethodMismatchError, IllegalOrderTransitionError) as exc:
            # Wrong method for the action, or the order is not in a shippable state.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except OrderError as exc:  # pragma: no cover - defensive (serializer + VO guard input)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_order_payload(order))


class ReadyForPickupView(APIView):
    """Mark a paid pickup (BOPIS) order ready for collection -- staff only."""

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="orders_ready_for_pickup",
        request=None,
        responses={
            200: OrderSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, number: str) -> Response:
        try:
            order = build_mark_order_ready_for_pickup().execute(
                FulfillmentActionCommand(number=number), actor=user_owner(request.user.pk)
            )
        except OrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except (FulfillmentMethodMismatchError, IllegalOrderTransitionError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(_order_payload(order))


class ConfirmPickupView(APIView):
    """Confirm a ready pickup order was collected (-> picked up) -- staff only."""

    permission_classes: ClassVar = [OrderManagePermission]

    @extend_schema(
        operation_id="orders_confirm_pickup",
        request=None,
        responses={
            200: OrderSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, number: str) -> Response:
        try:
            order = build_confirm_order_pickup().execute(
                FulfillmentActionCommand(number=number), actor=user_owner(request.user.pk)
            )
        except OrderNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except IllegalOrderTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(_order_payload(order))


class OrderCollectionView(APIView):
    """List the current shopper's orders, or place a new one (checkout) -- user or guest."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="orders_list",
        parameters=[
            OpenApiParameter(name="limit", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="offset", type=int, location=OpenApiParameter.QUERY),
        ],
        responses={200: OrderPageSerializer, 400: ErrorSerializer},
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
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = PlaceOrderCommand(
            owner=_owner(request),
            channel=data["channel"],
            shipping_method=data["shipping_method"],
            address_id=data.get("address_id"),
            shipping_address=_inline_shipping(data),
        )
        try:
            order = build_place_order().execute(command)
        except (
            UnknownChannelError,
            UnknownShippingAddressError,
            UnknownShippingMethodError,
        ) as exc:
            # A well-formed request-body reference (channel, saved address, or shipping
            # method) that does not resolve for this shopper. A not-owned address resolves
            # to the same error as a nonexistent one, so checkout never reveals whether
            # another shopper's address id exists.
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
    """Read one of the current shopper's orders by number (user or guest)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="orders_retrieve",
        responses={200: OrderSerializer, 404: ErrorSerializer},
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
    """Cancel one of the current shopper's still-pending orders (user or guest)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="orders_cancel",
        request=None,
        responses={
            200: OrderSerializer,
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
