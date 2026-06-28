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
