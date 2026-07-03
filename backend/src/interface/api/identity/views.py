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

import contextlib
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

from src.application.cart.use_cases import MergeGuestCartCommand
from src.application.identity.use_cases import RegisteredUser
from src.domain.identity.enums import OtpPurpose
from src.domain.identity.exceptions import (
    InvalidOtpError,
    InvalidPhoneNumberError,
    OtpError,
    OtpExpiredError,
    OtpMaxAttemptsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.domain.identity.value_objects import PhoneNumber
from src.infrastructure.identity.models import User
from src.interface.api.cart.container import build_merge_guest_cart
from src.interface.api.common import ErrorSerializer
from src.interface.api.guest import GUEST_OWNER_PREFIX, clear_guest_cookie, user_owner
from src.interface.api.identity.container import (
    build_register_user,
    build_request_otp,
    build_reset_password,
)
from src.interface.api.identity.cookies import clear_auth_cookies, set_auth_cookies
from src.interface.api.identity.serializers import (
    LoginSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    RequestOtpSerializer,
    UserSerializer,
)

logger = structlog.get_logger(__name__)

_INVALID_CREDENTIALS = "invalid credentials"
_INVALID_PHONE = "invalid phone number"
_OTP_REQUESTED = "if the phone number is eligible, a verification code has been sent"
_PASSWORD_RESET_DONE = "if the code was valid, the password has been reset"  # nosec B105 - a user-facing message, not a credential
_REGISTRATION_FAILED = "registration could not be completed"
_RESET_FAILED = "password reset could not be completed"

# OTP verification failures map to a 400 with a specific-but-safe message: the
# caller already holds a code, so distinguishing wrong/expired/locked leaks no
# account-existence information.
_OTP_ERROR_MESSAGES: dict[type[OtpError], str] = {
    InvalidOtpError: "invalid verification code",
    OtpExpiredError: "the verification code has expired",
    OtpMaxAttemptsError: "too many incorrect attempts; request a new code",
}


def _bad_request(detail: str) -> Response:
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _otp_error_response(exc: OtpError) -> Response:
    return _bad_request(_OTP_ERROR_MESSAGES[type(exc)])


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
        set_auth_cookies(response, access=str(refresh.access_token), refresh=str(refresh))
        self._merge_guest_cart(request, response, user)
        logger.info("login_succeeded", user_id=user.id)
        return response

    @staticmethod
    def _merge_guest_cart(request: Request, response: Response, user: User) -> None:
        """Fold a guest cart into the just-signed-in user's cart, then drop the cookie.

        Best-effort: a cart merge must never break authentication, so any failure is
        logged and swallowed and the guest cookie is *kept* (so the cart is not lost).
        The cookie is cleared only after a successful merge -- the guest identity is
        then spent.
        """
        token = request.COOKIES.get(settings.GUEST_COOKIE_NAME)
        if not token:
            return
        try:
            build_merge_guest_cart().execute(
                MergeGuestCartCommand(
                    guest_owner=f"{GUEST_OWNER_PREFIX}{token}",
                    user_owner=user_owner(user.pk),
                )
            )
        except Exception:
            logger.warning("guest_cart_merge_failed", user_id=user.id)
            return
        clear_guest_cookie(response)

    @staticmethod
    def _rejected() -> Response:
        return Response({"detail": _INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED)


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
            return Response({"detail": _INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(raw_refresh)
        except TokenError:
            return Response({"detail": _INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response(status=status.HTTP_200_OK)
        set_auth_cookies(response, access=str(refresh.access_token))
        return response


class LogoutView(APIView):
    """Blacklist the refresh token and clear the token cookies."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    # Logout just clears cookies; never reject it over a stale/invalid token.
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="The token cookies are cleared.")},
    )
    def post(self, request: Request) -> Response:
        # Best-effort revocation: a missing or already-invalid refresh token must
        # not fail logout -- the cookies are cleared regardless.
        raw_refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if raw_refresh:
            with contextlib.suppress(TokenError):
                RefreshToken(raw_refresh).blacklist()
        response = Response(status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        return response


class MeView(APIView):
    """Return the currently authenticated user."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer, 401: ErrorSerializer})
    def get(self, request: Request) -> Response:
        return Response(_user_payload(cast(User, request.user)))


class RequestOtpView(APIView):
    """Request a one-time code for registration or password reset.

    The response is uniform (``202`` with a generic message) whether or not a
    code was actually sent, so the endpoint never reveals which phone numbers
    have accounts.
    """

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=RequestOtpSerializer,
        responses={
            202: OpenApiResponse(description=_OTP_REQUESTED),
            400: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = RequestOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purpose = OtpPurpose(serializer.validated_data["purpose"])
        try:
            build_request_otp().execute(
                phone_number_raw=serializer.validated_data["phone_number"], purpose=purpose
            )
        except InvalidPhoneNumberError:
            return _bad_request(_INVALID_PHONE)
        return Response({"detail": _OTP_REQUESTED}, status=status.HTTP_202_ACCEPTED)


class RegisterView(APIView):
    """Create an account after verifying a registration code."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=RegisterSerializer,
        responses={201: UserSerializer, 400: ErrorSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            registered = build_register_user().execute(
                phone_number_raw=data["phone_number"],
                code=data["code"],
                password=data["password"],
                full_name=data["full_name"],
                email=data["email"],
            )
        except InvalidPhoneNumberError:
            return _bad_request(_INVALID_PHONE)
        except OtpError as exc:
            return _otp_error_response(exc)
        except UserAlreadyExistsError:
            logger.info("registration_rejected", reason="already_exists")
            return _bad_request(_REGISTRATION_FAILED)
        return Response(_registered_payload(registered), status=status.HTTP_201_CREATED)


class PasswordResetView(APIView):
    """Set a new password after verifying a reset code."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    authentication_classes: ClassVar[list] = []

    @extend_schema(
        request=PasswordResetSerializer,
        responses={
            200: OpenApiResponse(description=_PASSWORD_RESET_DONE),
            400: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            build_reset_password().execute(
                phone_number_raw=data["phone_number"],
                code=data["code"],
                new_password=data["new_password"],
            )
        except InvalidPhoneNumberError:
            return _bad_request(_INVALID_PHONE)
        except OtpError as exc:
            return _otp_error_response(exc)
        except UserNotFoundError:
            logger.info("password_reset_rejected", reason="unknown_user")
            return _bad_request(_RESET_FAILED)
        return Response({"detail": _PASSWORD_RESET_DONE}, status=status.HTTP_200_OK)


def _registered_payload(registered: RegisteredUser) -> dict[str, object]:
    return {
        "id": registered.id,
        "phone_number": registered.phone_number,
        "email": registered.email,
        "full_name": registered.full_name,
        "is_staff": False,
    }
