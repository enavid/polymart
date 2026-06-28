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

from src.application.access.use_cases import AssignRole, GrantChannelManagement
from src.domain.access.registry import CHANNEL_ADMIN_ROLE
from src.infrastructure.access.gateway import GuardianAccessControl
from src.infrastructure.channel.repositories import DjangoChannelRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def admin_user() -> AbstractBaseUser:
    """A global channel manager (channel_admin role): may manage every channel."""
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    AssignRole(GuardianAccessControl()).execute(user_id=user.pk, role_name=CHANNEL_ADMIN_ROLE)
    return user


@pytest.fixture
def auth_client(admin_user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def member_client() -> APIClient:
    """A plain authenticated user: may read channels but not mutate them."""
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
    """Two-layer RBAC: reads need only authentication; writes need the
    ``manage_channel`` permission, globally (role) or per-channel (guardian)."""

    def test_member_can_list_channels(self, member_client: APIClient) -> None:
        response = member_client.get("/api/v1/channels/")

        assert response.status_code == 200

    def test_member_can_retrieve_a_channel(
        self, member_client: APIClient, auth_client: APIClient
    ) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = member_client.get("/api/v1/channels/coffee/")

        assert response.status_code == 200

    def test_member_without_permission_cannot_create_a_channel(
        self, member_client: APIClient
    ) -> None:
        response = member_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 403

    def test_member_without_permission_cannot_change_status(
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

    def test_object_scoped_manager_can_change_its_own_channel(self, auth_client: APIClient) -> None:
        # An admin creates two channels; a fresh user is scoped to only one.
        for slug, name in (("coffee", "Coffee"), ("tea", "Tea")):
            auth_client.post(
                "/api/v1/channels/",
                {"slug": slug, "name": name, "currency": "IRR"},
                format="json",
            )
        scoped_user = get_user_model().objects.create_user(
            phone_number="09120000003", password="pw"
        )
        GrantChannelManagement(GuardianAccessControl(), DjangoChannelRepository()).execute(
            user_id=scoped_user.pk, channel_slug="coffee"
        )
        scoped_client = APIClient()
        scoped_client.force_authenticate(user=scoped_user)

        granted = scoped_client.patch(
            "/api/v1/channels/coffee/", {"is_active": False}, format="json"
        )
        # The same scope must NOT extend to a channel it was not granted.
        denied = scoped_client.patch("/api/v1/channels/tea/", {"is_active": False}, format="json")

        assert granted.status_code == 200
        assert granted.data["is_active"] is False
        assert denied.status_code == 403

    def test_object_scoped_manager_still_cannot_create_channels(
        self, auth_client: APIClient
    ) -> None:
        # Creating a channel is a platform-global action: object scope does not
        # confer it, even for a user who manages an existing channel.
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )
        scoped_user = get_user_model().objects.create_user(
            phone_number="09120000004", password="pw"
        )
        GrantChannelManagement(GuardianAccessControl(), DjangoChannelRepository()).execute(
            user_id=scoped_user.pk, channel_slug="coffee"
        )
        scoped_client = APIClient()
        scoped_client.force_authenticate(user=scoped_user)

        response = scoped_client.post(
            "/api/v1/channels/",
            {"slug": "tea", "name": "Tea", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 403


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
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        with capture_logs() as logs:
            auth_client.post(
                "/api/v1/channels/",
                {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
                format="json",
            )

        events = [entry for entry in logs if entry["event"] == "channel_created"]
        # The audit trail records the stable user id, not the phone number (PII).
        assert events and events[0]["actor"] == str(admin_user.pk)

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
