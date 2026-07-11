"""Tax endpoints (thin transport adapters).

The storefront needs a channel's tax rate so it can tell the shopper "prices include X%
VAT". The rate is public (no owner, no auth): it is channel configuration, not shopper data.
The view parses the channel, delegates to the use case, and projects the result -- no
business logic.
"""

from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.interface.api.common import ErrorSerializer
from src.interface.api.tax.container import build_get_tax_rate
from src.interface.api.tax.serializers import TaxRateSerializer


class TaxRateView(APIView):
    """Read the tax rate a channel levies (public)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="tax_rate_get",
        parameters=[
            OpenApiParameter(
                name="channel", type=str, location=OpenApiParameter.QUERY, required=True
            ),
        ],
        responses={200: TaxRateSerializer, 400: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        channel = request.query_params.get("channel", "").strip()
        if not channel:
            return Response(
                {"detail": "channel is required."},
                status=400,
            )
        rate = build_get_tax_rate().execute(channel=channel)
        return Response({"channel": channel, "rate": str(rate.value) if rate is not None else None})
