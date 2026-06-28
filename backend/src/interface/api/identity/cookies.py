"""Helpers for writing and clearing the JWT auth cookies.

Centralized so every endpoint sets identical, secure cookie attributes (HttpOnly,
SameSite, Secure-in-prod) instead of repeating them per view.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.response import Response


def set_auth_cookies(response: Response, *, access: str, refresh: str | None = None) -> None:
    """Attach the access (and optionally refresh) token as HttpOnly cookies."""
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS,
        access,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path=settings.AUTH_COOKIE_PATH,
    )
    if refresh is not None:
        response.set_cookie(
            settings.AUTH_COOKIE_REFRESH,
            refresh,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            httponly=settings.AUTH_COOKIE_HTTPONLY,
            secure=settings.AUTH_COOKIE_SECURE,
            samesite=settings.AUTH_COOKIE_SAMESITE,
            path=settings.AUTH_COOKIE_PATH,
        )


def clear_auth_cookies(response: Response) -> None:
    """Expire both token cookies (logout)."""
    for name in (settings.AUTH_COOKIE_ACCESS, settings.AUTH_COOKIE_REFRESH):
        response.delete_cookie(
            name,
            path=settings.AUTH_COOKIE_PATH,
            samesite=settings.AUTH_COOKIE_SAMESITE,
        )
