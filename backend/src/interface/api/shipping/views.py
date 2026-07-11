"""Shipping endpoints (thin transport adapters).

The storefront needs the delivery methods a channel offers so the shopper can pick one at
checkout. The list is public (no owner, no auth): it is channel configuration, not shopper
data. The view parses the channel, delegates to the use case, and projects the result --
no business logic.
"""

from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.shipping.use_cases import ListShippingMethodsQuery
from src.domain.shipping.entities import ShippingMethod
from src.interface.api.common import ErrorSerializer
from src.interface.api.shipping.container import build_list_shipping_methods
from src.interface.api.shipping.serializers import (
    ShippingMethodsQuerySerializer,
    ShippingMethodsSerializer,
)


def _method_payload(method: ShippingMethod) -> dict[str, object]:
    """Project a shipping method to the response body (price as an exact string)."""
    return {
        "code": method.code.value,
        "name": method.name,
        "price": str(method.price.amount),
        "currency": method.price.currency,
        "min_days": method.min_days,
        "max_days": method.max_days,
    }


class ShippingMethodCollectionView(APIView):
    """List the shipping methods a channel offers (public)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="shipping_methods_list",
        parameters=[
            OpenApiParameter(
                name="channel", type=str, location=OpenApiParameter.QUERY, required=True
            ),
        ],
        responses={200: ShippingMethodsSerializer, 400: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = ShippingMethodsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        channel = params.validated_data["channel"]
        methods = build_list_shipping_methods().execute(ListShippingMethodsQuery(channel=channel))
        return Response({"channel": channel, "methods": [_method_payload(m) for m in methods]})
