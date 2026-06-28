"""Authentication endpoints (thin transport over SimpleJWT).

Token issuance/validation is framework glue (SimpleJWT), so these views stay
deliberately thin per the project's pragmatism rule: validate input, normalize
the phone through the domain rule, authenticate, and move the resulting tokens
into HttpOnly cookies. No business logic lives here.

Auth failures return a uniform 401 regardless of cause (unknown user, wrong
password, malformed phone) so the endpoint does not leak whether an account
exists.
"""
from __future__ import annotations

from typing import ClassVar, cast

import structlog
from django.conf import settings
from django.contrib.auth import authenticate
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from src.domain.identity.exceptions import InvalidPhoneNumberError
from src.domain.identity.value_objects import PhoneNumber
from src.infrastructure.identity.models import User
from src.interface.api.common import ErrorSerializer
from src.interface.api.identity.cookies import clear_auth_cookies, set_auth_cookies
from src.interface.api.identity.serializers import LoginSerializer, UserSerializer

logger = structlog.get_logger(__name__)

_INVALID_CREDENTIALS = "invalid credentials"


def _user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "full_name": user.full_name,
        "is_staff": user.is_staff,
    }


class LoginView(APIView):
    """Exchange phone + password for token cookies."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    # Do not run cookie auth here: the browser auto-sends a possibly-expired
    # access cookie, and validating it would reject the login with a 401.
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=LoginSerializer,
        responses={200: UserSerializer, 400: ErrorSerializer, 401: ErrorSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data["password"]

        try:
            phone = PhoneNumber(serializer.validated_data["phone_number"]).value
        except InvalidPhoneNumberError:
            # Do not reveal that the phone was malformed vs. simply unknown.
            return self._rejected()

        user = authenticate(request, phone_number=phone, password=password)
        if user is None:
            logger.info("login_failed")
            return self._rejected()

        refresh = RefreshToken.for_user(user)
        response = Response(_user_payload(user), status=status.HTTP_200_OK)
        set_auth_cookies(
            response, access=str(refresh.access_token), refresh=str(refresh)
        )
        logger.info("login_succeeded", user_id=user.id)
        return response

    @staticmethod
    def _rejected() -> Response:
        return Response(
            {"detail": _INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
        )


class RefreshView(APIView):
    """Mint a fresh access cookie from the refresh cookie."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    # Refresh reads the refresh cookie explicitly; a stale access cookie must not
    # short-circuit it via the auth layer.
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="A fresh access-token cookie is set."),
            401: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        raw_refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not raw_refresh:
            return Response(
                {"detail": _INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            refresh = RefreshToken(raw_refresh)
        except TokenError:
            return Response(
                {"detail": _INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED
            )

        response = Response(status=status.HTTP_200_OK)
        set_auth_cookies(response, access=str(refresh.access_token))
        return response


class LogoutView(APIView):
    """Clear the token cookies."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    # Logout just clears cookies; never reject it over a stale/invalid token.
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="The token cookies are cleared.")},
    )
    def post(self, request: Request) -> Response:
        response = Response(status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    """Return the currently authenticated user."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer, 401: ErrorSerializer})
    def get(self, request: Request) -> Response:
        return Response(_user_payload(cast(User, request.user)))
