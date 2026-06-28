"""Channel endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result. They hold
no business logic. Domain exceptions are translated to HTTP status codes here --
the one place where the domain meets the transport.
"""
from __future__ import annotations

import structlog
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.channel.use_cases import CreateChannelCommand
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import (
    ChannelAlreadyExistsError,
    ChannelError,
    ChannelNotFoundError,
)
from src.interface.api.channel.container import (
    build_create_channel,
    build_get_channel,
    build_list_channels,
    build_set_channel_status,
)
from src.interface.api.channel.serializers import (
    ChannelSerializer,
    CreateChannelSerializer,
    SetChannelStatusSerializer,
)
from src.interface.api.common import ErrorSerializer

logger = structlog.get_logger(__name__)

# Query-string flags arrive as strings; accept the conventional truthy spellings
# rather than only the literal "true".
_TRUTHY_QUERY_VALUES = frozenset({"true", "1", "yes", "on"})


def _query_flag(raw: str | None) -> bool:
    """Interpret a query-string flag value as a boolean."""
    return raw is not None and raw.strip().lower() in _TRUTHY_QUERY_VALUES


def _actor(request: Request) -> str | None:
    """Identify the authenticated user behind a mutation for the audit trail."""
    user = request.user
    return user.get_username() if user.is_authenticated else None


class _AdminWriteMixin:
    """Reads need authentication; writes need staff (admin) privileges.

    Channels are platform-level configuration: deactivating one takes a storefront
    offline. The project-wide RBAC layer (identity slice) will supersede this with
    fine-grained, channel-scoped permissions; until then mutations are limited to
    staff while reads stay open to any authenticated user.
    """

    # Provided by APIView at runtime; declared here for the type checker.
    request: Request

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAdminUser()]


def _payload(channel: Channel) -> dict[str, object]:
    """Project a domain entity to the response body.

    This is the single source of the response shape; ``ChannelSerializer`` exists
    only to document that shape in the OpenAPI schema (the domain entity, with its
    value objects, cannot be fed to a serializer directly).
    """
    return {
        "id": channel.id,
        "slug": channel.slug.value,
        "name": channel.name,
        "currency": channel.currency.code,
        "is_active": channel.is_active,
    }


class ChannelListCreateView(_AdminWriteMixin, APIView):
    """List channels or create a new one."""

    @extend_schema(responses=ChannelSerializer(many=True))
    def get(self, request: Request) -> Response:
        only_active = _query_flag(request.query_params.get("active"))
        channels = build_list_channels().execute(only_active=only_active)
        return Response([_payload(channel) for channel in channels])

    @extend_schema(
        request=CreateChannelSerializer,
        responses={
            201: ChannelSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateChannelCommand(
            name=data["name"],
            slug=data["slug"],
            currency=data["currency"],
            is_active=data["is_active"],
        )
        try:
            channel = build_create_channel().execute(command, actor=_actor(request))
        except ChannelAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ChannelError as exc:
            # Invalid slug/currency/name surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_payload(channel), status=status.HTTP_201_CREATED)


class ChannelDetailView(_AdminWriteMixin, APIView):
    """Retrieve a channel or change its active status."""

    @extend_schema(responses={200: ChannelSerializer, 404: ErrorSerializer})
    def get(self, request: Request, slug: str) -> Response:
        try:
            channel = build_get_channel().execute(slug=slug)
        except ChannelNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payload(channel))

    @extend_schema(
        request=SetChannelStatusSerializer,
        responses={
            200: ChannelSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def patch(self, request: Request, slug: str) -> Response:
        serializer = SetChannelStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            channel = build_set_channel_status().execute(
                slug=slug,
                active=serializer.validated_data["is_active"],
                actor=_actor(request),
            )
        except ChannelNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payload(channel))
