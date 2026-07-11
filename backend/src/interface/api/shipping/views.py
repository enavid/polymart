"""Shipping endpoints (thin transport adapters).

The storefront needs the delivery methods a channel offers so the shopper can pick one at
checkout. The list is public (no owner, no auth): it is channel configuration, not shopper
data. The view parses the channel, delegates to the use case, and projects the result --
no business logic.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.shipping.use_cases import ListShippingMethodsQuery
from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.exceptions import InvalidDestinationError
from src.domain.shipping.value_objects import Destination
from src.interface.api.common import ErrorSerializer
from src.interface.api.shipping.container import build_list_shipping_methods
from src.interface.api.shipping.serializers import (
    ShippingMethodsQuerySerializer,
    ShippingMethodsSerializer,
)

logger = structlog.get_logger(__name__)


def _destination_from(province: str, city: str) -> Destination | None:
    """Build a destination from the query, or ``None`` (default rates) if there is no province.

    A malformed province degrades to ``None`` (the default rates) rather than a 400: listing
    methods is a read that should still succeed, and the authoritative rate is re-resolved
    from the captured address at checkout regardless.
    """
    if not province.strip():
        return None
    try:
        return Destination(province=province, city=city)
    except InvalidDestinationError:
        logger.warning("shipping_destination_invalid", province_length=len(province))
        return None


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
            OpenApiParameter(
                name="province", type=str, location=OpenApiParameter.QUERY, required=False
            ),
            OpenApiParameter(
                name="city", type=str, location=OpenApiParameter.QUERY, required=False
            ),
        ],
        responses={200: ShippingMethodsSerializer, 400: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = ShippingMethodsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        channel = params.validated_data["channel"]
        destination = _destination_from(
            params.validated_data.get("province", ""),
            params.validated_data.get("city", ""),
        )
        methods = build_list_shipping_methods().execute(
            ListShippingMethodsQuery(channel=channel, destination=destination)
        )
        return Response({"channel": channel, "methods": [_method_payload(m) for m in methods]})
