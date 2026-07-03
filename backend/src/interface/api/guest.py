"""Guest (anonymous) ownership for the cart, backed by an HttpOnly session cookie.

The cart/order application layer keys aggregates by an opaque string ``owner``. This
module is the single place that decides what that string is for a given HTTP request
and how a brand-new guest is remembered:

- an authenticated request owns by ``u:<pk>`` (the user's stable primary key);
- a guest owns by ``g:<token>``, where ``token`` is a CSPRNG value carried in an
  HttpOnly cookie that the backend mints on the guest's first cart write.

The token is the credential -- it is unguessable and never leaves an HttpOnly,
SameSite cookie -- so a guest can reach only their own cart, exactly as a user can
reach only theirs. There is no owner id in any URL, so cross-owner access (IDOR)
stays structurally impossible for guests and users alike.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response

USER_OWNER_PREFIX = "u:"
GUEST_OWNER_PREFIX = "g:"

# 32 bytes -> ~43 url-safe base64 characters: far beyond brute-force reach.
_GUEST_TOKEN_BYTES = 32


@dataclass(frozen=True)
class OwnerResolution:
    """The resolved cart owner id, plus a guest token to persist if one was minted.

    ``owner`` is the opaque, prefixed id the application layer keys the cart by.
    ``set_cookie`` is the raw guest token the caller must write to the response cookie
    -- populated only when a fresh guest identity was minted (a guest's first cart
    write). It is ``None`` for authenticated requests and for guest reads, so those
    never set a cookie.
    """

    owner: str
    set_cookie: str | None = None


def user_owner(pk: object) -> str:
    """The owner id for an authenticated user: their primary key, prefixed."""
    return f"{USER_OWNER_PREFIX}{pk}"


def resolve_owner(request: Request, *, mint: bool) -> OwnerResolution:
    """Resolve the owner of the cart for this request.

    Authenticated -> ``u:<pk>`` and never mints a cookie. Guest with an existing
    session cookie -> ``g:<token>``. Guest without one: when ``mint`` is true (a write
    that will persist a cart) a fresh CSPRNG token is generated and returned in
    ``set_cookie`` for the caller to store; when false (a read) a throwaway token is
    used that matches no stored row, so a cookieless guest reads an empty cart without
    being tagged with a tracking cookie.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return OwnerResolution(owner=user_owner(user.pk))
    existing = request.COOKIES.get(settings.GUEST_COOKIE_NAME)
    if existing:
        return OwnerResolution(owner=f"{GUEST_OWNER_PREFIX}{existing}")
    token = secrets.token_urlsafe(_GUEST_TOKEN_BYTES)
    return OwnerResolution(
        owner=f"{GUEST_OWNER_PREFIX}{token}",
        set_cookie=token if mint else None,
    )


def set_guest_cookie(response: Response, token: str) -> None:
    """Persist a freshly minted guest session token as an HttpOnly cookie.

    Mirrors the auth cookies' Secure/SameSite/Path posture so the guest credential is
    protected identically (no JS access, same-site only, Secure outside DEBUG).
    """
    response.set_cookie(
        settings.GUEST_COOKIE_NAME,
        token,
        max_age=settings.GUEST_COOKIE_MAX_AGE,
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path=settings.AUTH_COOKIE_PATH,
    )


def clear_guest_cookie(response: Response) -> None:
    """Expire the guest session cookie.

    Sent on login once the guest cart has been merged into the user's: the guest
    identity is spent, so the credential must not linger in the browser. Matches the
    cookie's Path/SameSite so the browser targets the right cookie to delete.
    """
    response.delete_cookie(
        settings.GUEST_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
