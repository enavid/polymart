"""Access-administration endpoints (thin transport adapters).

Assign a global role to a user, or grant a user object-scoped management of a
single channel. Both are gated by the global ``manage_access`` permission and
delegate to audited use cases; the views hold no business logic and only map
domain exceptions to HTTP status codes.
"""

from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.domain.access.exceptions import RoleNotFoundError, SubjectNotFoundError
from src.domain.channel.exceptions import ChannelNotFoundError
from src.interface.api.access.container import (
    build_assign_role,
    build_grant_channel_management,
)
from src.interface.api.access.permissions import AccessAdminPermission
from src.interface.api.access.serializers import (
    AssignRoleSerializer,
    GrantChannelManagementSerializer,
)
from src.interface.api.common import ErrorSerializer


def _actor(request: Request) -> str | None:
    """Identify the acting administrator for the audit trail (stable id, not PII)."""
    user = request.user
    return str(user.pk) if user.is_authenticated else None


class RoleAssignmentView(APIView):
    """Assign a global role (Django Group) to a user."""

    permission_classes: ClassVar = [AccessAdminPermission]

    @extend_schema(
        request=AssignRoleSerializer,
        responses={
            200: OpenApiResponse(description="The role was assigned."),
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            build_assign_role().execute(
                user_id=data["user_id"], role_name=data["role"], actor=_actor(request)
            )
        except SubjectNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except RoleNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)


class ChannelGrantView(APIView):
    """Grant a user object-scoped management of a single channel."""

    permission_classes: ClassVar = [AccessAdminPermission]

    @extend_schema(
        request=GrantChannelManagementSerializer,
        responses={
            200: OpenApiResponse(description="The channel grant was recorded."),
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = GrantChannelManagementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            build_grant_channel_management().execute(
                user_id=data["user_id"],
                channel_slug=data["channel_slug"],
                actor=_actor(request),
            )
        except (SubjectNotFoundError, ChannelNotFoundError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_200_OK)
