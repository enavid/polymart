"""Integration tests for the cookie-based JWT auth endpoints (full HTTP path).

These pin the security posture: tokens are delivered as HttpOnly cookies (not
readable by JS, not echoed in the body), credentials are never logged, and the
cookie carries the session so a follow-up request is authenticated.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from structlog.testing import capture_logs

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

PASSWORD = "s3cret-pw"


@pytest.fixture
def user() -> object:
    return get_user_model().objects.create_user(phone_number="09123456789", password=PASSWORD)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


class TestLogin:
    def test_login_succeeds_and_sets_httponly_token_cookies(
        self, client: APIClient, user: object
    ) -> None:
        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 200
        access = response.cookies[settings.AUTH_COOKIE_ACCESS]
        refresh = response.cookies[settings.AUTH_COOKIE_REFRESH]
        assert access["httponly"] is True
        assert refresh["httponly"] is True
        assert access["samesite"] == settings.AUTH_COOKIE_SAMESITE

    def test_login_does_not_leak_tokens_in_the_response_body(
        self, client: APIClient, user: object
    ) -> None:
        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

        assert "access" not in response.data
        assert "refresh" not in response.data
        assert response.data["phone_number"] == "+989123456789"

    def test_login_accepts_any_spelling_of_the_phone_number(
        self, client: APIClient, user: object
    ) -> None:
        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "+989123456789", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 200

    def test_wrong_password_is_rejected_without_a_cookie(
        self, client: APIClient, user: object
    ) -> None:
        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": "wrong"},
            format="json",
        )

        assert response.status_code == 401
        assert settings.AUTH_COOKIE_ACCESS not in response.cookies

    def test_unknown_user_is_rejected(self, client: APIClient) -> None:
        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09120000000", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 401

    def test_malformed_phone_is_rejected_as_invalid_credentials(self, client: APIClient) -> None:
        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "not-a-phone", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 401

    def test_missing_fields_return_400(self, client: APIClient) -> None:
        response = client.post(
            "/api/v1/auth/login/", {"phone_number": "09123456789"}, format="json"
        )

        assert response.status_code == 400

    def test_inactive_user_cannot_log_in(self, client: APIClient) -> None:
        get_user_model().objects.create_user(
            phone_number="09120000001", password=PASSWORD, is_active=False
        )

        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09120000001", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 401

    def test_login_works_even_with_a_stale_access_cookie(
        self, client: APIClient, user: object
    ) -> None:
        # The browser auto-sends a possibly-expired access cookie. Login must not
        # be blocked by the auth layer trying (and failing) to validate it.
        client.cookies[settings.AUTH_COOKIE_ACCESS] = "expired-or-garbage-token"

        response = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 200

    def test_password_is_never_logged(self, client: APIClient, user: object) -> None:
        with capture_logs() as logs:
            client.post(
                "/api/v1/auth/login/",
                {"phone_number": "09123456789", "password": PASSWORD},
                format="json",
            )

        serialized = repr(logs)
        assert PASSWORD not in serialized


class TestLoginMergesGuestCart:
    """On login, a cart the shopper built as a guest is folded into their user cart."""

    _CHANNEL = "ir-main"
    _GUEST_TOKEN = "guest-merge-token"

    def _login(self, client: APIClient) -> object:
        return client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

    def _guest_cart_with_a_line(self) -> object:
        from src.domain.cart.value_objects import CartQuantity, Sku
        from src.infrastructure.cart.repositories import DjangoCartRepository

        repo = DjangoCartRepository()
        repo.apply(
            f"g:{self._GUEST_TOKEN}",
            self._CHANNEL,
            lambda cart: cart.add_item(Sku("HB-250"), CartQuantity(2)),
        )
        return repo

    def test_login_merges_the_guest_cart_and_clears_the_cookie(
        self, client: APIClient, user: object
    ) -> None:
        from src.infrastructure.cart.models import CartModel

        repo = self._guest_cart_with_a_line()
        client.cookies[settings.GUEST_COOKIE_NAME] = self._GUEST_TOKEN

        response = self._login(client)

        assert response.status_code == 200
        # The guest identity is spent -- the cookie is expired on the response.
        assert response.cookies[settings.GUEST_COOKIE_NAME]["max-age"] == 0
        # The line now belongs to the user; the guest cart row is gone.
        user_cart = repo.get(f"u:{user.pk}", self._CHANNEL)  # type: ignore[attr-defined]
        assert [(line.sku.value, line.quantity.value) for line in user_cart.lines] == [
            ("HB-250", 2)
        ]
        assert not CartModel.objects.filter(guest_token=self._GUEST_TOKEN).exists()

    def test_login_without_a_guest_cookie_touches_no_cookie(
        self, client: APIClient, user: object
    ) -> None:
        response = self._login(client)

        assert response.status_code == 200
        assert settings.GUEST_COOKIE_NAME not in response.cookies

    def test_a_failing_merge_never_breaks_login(
        self, client: APIClient, user: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A cart merge is best-effort: if it blows up, authentication still succeeds
        # and the guest cookie is kept (so the cart is not silently lost).
        from src.interface.api.identity import views

        def _boom() -> object:
            raise RuntimeError("merge exploded")

        monkeypatch.setattr(views, "build_merge_guest_cart", _boom)
        client.cookies[settings.GUEST_COOKIE_NAME] = self._GUEST_TOKEN

        response = self._login(client)

        assert response.status_code == 200
        assert settings.GUEST_COOKIE_NAME not in response.cookies


class TestMe:
    def test_cookie_authenticates_a_follow_up_request(
        self, client: APIClient, user: object
    ) -> None:
        client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

        response = client.get("/api/v1/auth/me/")

        assert response.status_code == 200
        assert response.data["phone_number"] == "+989123456789"

    def test_me_requires_authentication(self, client: APIClient) -> None:
        assert client.get("/api/v1/auth/me/").status_code == 401


class TestRefresh:
    def test_refresh_cookie_issues_a_new_access_cookie(
        self, client: APIClient, user: object
    ) -> None:
        client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

        response = client.post("/api/v1/auth/refresh/")

        assert response.status_code == 200
        assert settings.AUTH_COOKIE_ACCESS in response.cookies

    def test_refresh_without_a_cookie_is_rejected(self, client: APIClient) -> None:
        assert client.post("/api/v1/auth/refresh/").status_code == 401

    def test_malformed_refresh_cookie_is_rejected(self, client: APIClient) -> None:
        client.cookies[settings.AUTH_COOKIE_REFRESH] = "not-a-valid-token"

        assert client.post("/api/v1/auth/refresh/").status_code == 401


class TestLogout:
    def test_logout_clears_the_token_cookies(self, client: APIClient, user: object) -> None:
        client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )

        response = client.post("/api/v1/auth/logout/")

        assert response.status_code == 200
        # A cleared cookie is sent back with an immediate expiry.
        assert response.cookies[settings.AUTH_COOKIE_ACCESS]["max-age"] == 0

    def test_logout_without_a_session_still_succeeds(self, client: APIClient) -> None:
        # No refresh cookie to revoke; logout must still clear cookies and 200.
        assert client.post("/api/v1/auth/logout/").status_code == 200

    def test_logout_blacklists_the_refresh_token(self, client: APIClient, user: object) -> None:
        # After logout the refresh token is revoked: presenting it again must not
        # mint a new access token, even though the raw token is still well-formed.
        login = client.post(
            "/api/v1/auth/login/",
            {"phone_number": "09123456789", "password": PASSWORD},
            format="json",
        )
        stale_refresh = login.cookies[settings.AUTH_COOKIE_REFRESH].value

        client.post("/api/v1/auth/logout/")

        client.cookies[settings.AUTH_COOKIE_REFRESH] = stale_refresh
        assert client.post("/api/v1/auth/refresh/").status_code == 401
