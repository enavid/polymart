"""Integration tests for the channel HTTP endpoints (full request path + DB).

These assert the secure-by-default posture (auth required), the happy paths, and
the mapping of domain errors to HTTP status codes.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_user() -> AbstractBaseUser:
    """A staff user: allowed to perform channel writes (admin-only operations)."""
    return get_user_model().objects.create_user(
        phone_number="09120000001", password="pw", is_staff=True
    )


@pytest.fixture
def auth_client(staff_user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


@pytest.fixture
def member_client() -> APIClient:
    """A non-staff authenticated user: may read channels but not mutate them."""
    user = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        response = APIClient().get("/api/v1/channels/")

        assert response.status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post("/api/v1/channels/", {}, format="json")

        assert response.status_code == 401

    def test_retrieving_requires_authentication(self) -> None:
        response = APIClient().get("/api/v1/channels/coffee/")

        assert response.status_code == 401

    def test_status_change_requires_authentication(self) -> None:
        response = APIClient().patch(
            "/api/v1/channels/coffee/", {"is_active": False}, format="json"
        )

        assert response.status_code == 401


class TestAuthorization:
    """Writes are admin-only; reads are open to any authenticated user."""

    def test_non_staff_user_can_list_channels(self, member_client: APIClient) -> None:
        response = member_client.get("/api/v1/channels/")

        assert response.status_code == 200

    def test_non_staff_user_cannot_create_a_channel(self, member_client: APIClient) -> None:
        response = member_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 403

    def test_non_staff_user_cannot_change_status(
        self, member_client: APIClient, auth_client: APIClient
    ) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = member_client.patch(
            "/api/v1/channels/coffee/", {"is_active": False}, format="json"
        )

        assert response.status_code == 403

    def test_non_staff_user_can_retrieve_a_channel(
        self, member_client: APIClient, auth_client: APIClient
    ) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = member_client.get("/api/v1/channels/coffee/")

        assert response.status_code == 200


class TestCreate:
    def test_creates_a_channel(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee Store", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["slug"] == "coffee"
        assert response.data["currency"] == "IRR"
        assert response.data["is_active"] is True
        assert response.data["id"] is not None

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, staff_user: AbstractBaseUser
    ) -> None:
        with capture_logs() as logs:
            auth_client.post(
                "/api/v1/channels/",
                {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
                format="json",
            )

        events = [entry for entry in logs if entry["event"] == "channel_created"]
        # The audit trail records the stable user id, not the phone number (PII).
        assert events and events[0]["actor"] == str(staff_user.pk)

    def test_duplicate_slug_returns_409(self, auth_client: APIClient) -> None:
        body = {"slug": "coffee", "name": "Coffee", "currency": "IRR"}
        auth_client.post("/api/v1/channels/", body, format="json")

        response = auth_client.post("/api/v1/channels/", body, format="json")

        assert response.status_code == 409

    def test_invalid_currency_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "toman"},
            format="json",
        )

        assert response.status_code == 400

    def test_invalid_slug_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/channels/",
            {"slug": "Not A Slug", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 400

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post("/api/v1/channels/", {"slug": "coffee"}, format="json")

        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_channels(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get("/api/v1/channels/")

        assert response.status_code == 200
        assert {c["slug"] for c in response.data} == {"coffee"}

    def test_can_filter_to_active_only(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {
                "slug": "draft",
                "name": "Draft",
                "currency": "IRR",
                "is_active": False,
            },
            format="json",
        )
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "live", "name": "Live", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get("/api/v1/channels/?active=true")

        assert {c["slug"] for c in response.data} == {"live"}

    @pytest.mark.parametrize("truthy", ["true", "True", "1", "yes", "on"])
    def test_active_filter_accepts_common_truthy_tokens(
        self, auth_client: APIClient, truthy: str
    ) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "draft", "name": "Draft", "currency": "IRR", "is_active": False},
            format="json",
        )
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "live", "name": "Live", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get(f"/api/v1/channels/?active={truthy}")

        assert {c["slug"] for c in response.data} == {"live"}

    def test_retrieves_a_single_channel(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get("/api/v1/channels/coffee/")

        assert response.status_code == 200
        assert response.data["name"] == "Coffee"

    def test_unknown_channel_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.get("/api/v1/channels/ghost/")

        assert response.status_code == 404


class TestStatusChange:
    def test_deactivates_a_channel(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = auth_client.patch(
            "/api/v1/channels/coffee/", {"is_active": False}, format="json"
        )

        assert response.status_code == 200
        assert response.data["is_active"] is False

    def test_status_change_on_unknown_channel_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.patch("/api/v1/channels/ghost/", {"is_active": False}, format="json")

        assert response.status_code == 404
