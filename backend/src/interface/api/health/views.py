"""Health endpoint view (thin transport adapter)."""
from __future__ import annotations

from typing import ClassVar

import structlog
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.domain.health.entities import HealthState
from src.interface.api.health.container import build_get_system_health
from src.interface.api.health.serializers import HealthReportSerializer

logger = structlog.get_logger(__name__)


class HealthView(APIView):
    """Liveness/readiness endpoint. Public by design."""

    permission_classes: ClassVar = [AllowAny]
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        responses={
            200: HealthReportSerializer,
            503: HealthReportSerializer,
        }
    )
    def get(self, request: Request) -> Response:
        report = build_get_system_health().execute()
        payload = {
            "state": report.state.value,
            "components": [
                {"name": c.name, "state": c.state.value, "detail": c.detail}
                for c in report.components
            ],
        }
        serializer = HealthReportSerializer(payload)
        http_status = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if report.state is HealthState.UNHEALTHY
            else status.HTTP_200_OK
        )
        # Probes poll this endpoint continuously, so a healthy result is logged at
        # debug to avoid flooding the logs; an unhealthy one is worth a warning.
        log = logger.warning if report.state is HealthState.UNHEALTHY else logger.debug
        log("health_check", state=report.state.value, status=http_status)
        return Response(serializer.data, status=http_status)
