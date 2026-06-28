"""Cookie-based JWT authentication.

SimpleJWT reads the access token from the ``Authorization`` header by default.
We instead carry it in an HttpOnly cookie so client-side JavaScript can never
read it, which removes the usual XSS token-theft vector. The header path is kept
as a fallback for non-browser API clients and tooling.
"""

from __future__ import annotations

from typing import Any, cast

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import Token


class CookieJWTAuthentication(JWTAuthentication):
    """Authenticate from the access-token cookie, falling back to the header."""

    def authenticate(self, request: Request) -> tuple[Any, Token] | None:
        raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
        if raw_token is None:
            # No cookie -- let the header-based path handle API clients/tooling.
            return super().authenticate(request)
        # The cookie value is str; SimpleJWT accepts it at runtime although its
        # stub annotates bytes.
        validated_token = self.get_validated_token(cast(bytes, raw_token))
        return self.get_user(validated_token), validated_token


class CookieJWTScheme(OpenApiAuthenticationExtension):
    """Document the access-token cookie as a security scheme in the OpenAPI doc.

    drf-spectacular auto-registers this on import (the auth class is imported when
    DRF builds its default authenticators), so the schema gains an honest
    ``cookieAuth`` definition instead of an unresolved-authenticator warning.
    """

    target_class = "src.interface.api.identity.authentication.CookieJWTAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.AUTH_COOKIE_ACCESS,
        }
