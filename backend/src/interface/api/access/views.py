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

from src.application.identity.admin_use_cases import (
    DEFAULT_PAGE_LIMIT as _DEFAULT_USER_PAGE_LIMIT,
)
from src.application.identity.admin_use_cases import (
    InvalidUserPageError,
    UserAccountPage,
)
from src.application.identity.ports import UserAccount
from src.domain.access.exceptions import RoleNotFoundError, SubjectNotFoundError
from src.domain.channel.exceptions import ChannelNotFoundError
from src.domain.identity.exceptions import (
    InvalidPhoneNumberError,
    UserAlreadyExistsError,
)
from src.interface.api.access.container import (
    build_admin_create_user,
    build_assign_role,
    build_grant_channel_management,
    build_list_user_accounts,
)
from src.interface.api.access.permissions import AccessAdminPermission
from src.interface.api.access.serializers import (
    AssignRoleSerializer,
    CreateUserSerializer,
    GrantChannelManagementSerializer,
    UserAccountPageSerializer,
    UserAccountSerializer,
    UserListQuerySerializer,
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


def _account_payload(account: UserAccount) -> dict[str, object]:
    """Project a user-account read model to the response body."""
    return {
        "id": account.id,
        "phone_number": account.phone_number,
        "full_name": account.full_name,
        "email": account.email,
        "is_staff": account.is_staff,
        "is_active": account.is_active,
    }


def _page_payload(page: UserAccountPage, *, limit: int, offset: int) -> dict[str, object]:
    """Project a page of user accounts to the response body."""
    return {
        "count": page.total,
        "limit": limit,
        "offset": offset,
        "results": [_account_payload(account) for account in page.items],
    }


class UserAdminView(APIView):
    """List user accounts or create one directly (access-admin user management).

    Backs the admin access panel's user picker so roles/grants can be applied to a
    chosen account instead of a raw id. Both verbs require ``manage_access``.
    """

    permission_classes: ClassVar = [AccessAdminPermission]

    @extend_schema(
        parameters=[UserListQuerySerializer],
        responses={200: UserAccountPageSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = UserListQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        # Resolve the effective window (mirroring the use case defaults) so the same
        # bounds are echoed back in the page envelope for the client's pagination.
        limit = data.get("limit", _DEFAULT_USER_PAGE_LIMIT)
        offset = data.get("offset", 0)
        try:
            page = build_list_user_accounts().execute(limit=limit, offset=offset)
        except InvalidUserPageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_page_payload(page, limit=limit, offset=offset))

    @extend_schema(
        request=CreateUserSerializer,
        responses={
            201: UserAccountSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            account = build_admin_create_user().execute(
                phone_number_raw=data["phone_number"],
                password=data["password"],
                full_name=data["full_name"],
                email=data["email"],
                is_staff=data["is_staff"],
                actor=_actor(request),
            )
        except UserAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InvalidPhoneNumberError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_account_payload(account), status=status.HTTP_201_CREATED)
