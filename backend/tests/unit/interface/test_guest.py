"""Unit tests for guest (anonymous) owner resolution.

Pure logic (no DB): given a request's auth state and cookies, decide the opaque
owner id the cart is keyed by and whether a fresh guest token must be persisted.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from src.interface.api.guest import (
    GUEST_OWNER_PREFIX,
    USER_OWNER_PREFIX,
    resolve_owner,
    user_owner,
)


@dataclass
class _FakeUser:
    pk: int
    is_authenticated: bool


class _FakeRequest:
    def __init__(self, *, user: _FakeUser | None, cookies: dict[str, str] | None = None) -> None:
        self.user = user
        self.COOKIES = cookies or {}


class TestResolveOwner:
    def test_authenticated_user_owns_by_prefixed_pk(self) -> None:
        request = _FakeRequest(user=_FakeUser(pk=7, is_authenticated=True))

        resolution = resolve_owner(request, mint=True)

        assert resolution.owner == f"{USER_OWNER_PREFIX}7"
        # An authenticated request never mints or touches a guest cookie.
        assert resolution.set_cookie is None

    def test_guest_with_existing_cookie_owns_by_that_token(self) -> None:
        request = _FakeRequest(
            user=_FakeUser(pk=0, is_authenticated=False),
            cookies={settings.GUEST_COOKIE_NAME: "existing-token"},
        )

        resolution = resolve_owner(request, mint=True)

        assert resolution.owner == f"{GUEST_OWNER_PREFIX}existing-token"
        # An already-identified guest is not re-minted.
        assert resolution.set_cookie is None

    def test_guest_write_without_cookie_mints_and_asks_to_persist(self) -> None:
        request = _FakeRequest(user=_FakeUser(pk=0, is_authenticated=False))

        resolution = resolve_owner(request, mint=True)

        assert resolution.owner.startswith(GUEST_OWNER_PREFIX)
        token = resolution.owner[len(GUEST_OWNER_PREFIX) :]
        assert token != ""
        # The minted token is handed back so the caller can set the cookie, and it
        # matches the owner (the cookie value is exactly the token in the owner id).
        assert resolution.set_cookie == token

    def test_guest_read_without_cookie_does_not_mint_a_cookie(self) -> None:
        request = _FakeRequest(user=_FakeUser(pk=0, is_authenticated=False))

        resolution = resolve_owner(request, mint=False)

        # A cookieless read still yields a (throwaway) owner so the empty-cart path
        # works, but must never tag the visitor with a tracking cookie.
        assert resolution.owner.startswith(GUEST_OWNER_PREFIX)
        assert resolution.set_cookie is None

    def test_minted_tokens_are_unforgeable_and_unique(self) -> None:
        request = _FakeRequest(user=_FakeUser(pk=0, is_authenticated=False))

        first = resolve_owner(request, mint=True)
        second = resolve_owner(request, mint=True)

        assert first.owner != second.owner
        # CSPRNG token: long enough that guessing another guest's cart is infeasible.
        assert len(first.set_cookie or "") >= 32

    def test_missing_user_attribute_is_treated_as_a_guest(self) -> None:
        # Defensive: a request without a resolved user (e.g. an unauthenticated
        # transport) is a guest, not a crash.
        request = _FakeRequest(user=None)

        resolution = resolve_owner(request, mint=True)

        assert resolution.owner.startswith(GUEST_OWNER_PREFIX)


class TestUserOwner:
    def test_prefixes_the_primary_key(self) -> None:
        assert user_owner(42) == f"{USER_OWNER_PREFIX}42"
