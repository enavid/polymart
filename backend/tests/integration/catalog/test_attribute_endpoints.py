"""Integration tests for the catalog attribute endpoints (full path + DB).

These assert the secure-by-default posture (auth required, global perm to
mutate), the happy paths, and the mapping of domain errors to HTTP status codes.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_TEXT_ATTRIBUTE = {"code": "origin", "name": "Origin", "input_type": "plain_text"}
_DROPDOWN_ATTRIBUTE = {
    "code": "roast-level",
    "name": "Roast level",
    "input_type": "dropdown",
    "choices": [
        {"value": "light", "label": "Light"},
        {"value": "dark", "label": "Dark"},
    ],
}


@pytest.fixture
def admin_user() -> AbstractBaseUser:
    """A catalog manager (catalog_admin role): may define the catalog schema."""
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    build_assign_role().execute(user_id=user.pk, role_name=CATALOG_ADMIN_ROLE)
    return user


@pytest.fixture
def auth_client(admin_user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def member_client() -> APIClient:
    """A plain authenticated user: may read attributes but not mutate them."""
    user = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        assert APIClient().get("/api/v1/catalog/attributes/").status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post("/api/v1/catalog/attributes/", {}, format="json")
        assert response.status_code == 401

    def test_retrieving_requires_authentication(self) -> None:
        assert APIClient().get("/api/v1/catalog/attributes/origin/").status_code == 401


class TestAuthorization:
    def test_member_can_list_attributes(self, member_client: APIClient) -> None:
        assert member_client.get("/api/v1/catalog/attributes/").status_code == 200

    def test_member_without_permission_cannot_create(self, member_client: APIClient) -> None:
        response = member_client.post(
            "/api/v1/catalog/attributes/", _TEXT_ATTRIBUTE, format="json"
        )
        assert response.status_code == 403


class TestCreate:
    def test_creates_a_text_attribute(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/", _TEXT_ATTRIBUTE, format="json"
        )

        assert response.status_code == 201
        assert response.data["code"] == "origin"
        assert response.data["input_type"] == "plain_text"
        assert response.data["required"] is False
        assert response.data["choices"] == []
        assert response.data["id"] is not None

    def test_creates_a_dropdown_with_choices(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/", _DROPDOWN_ATTRIBUTE, format="json"
        )

        assert response.status_code == 201
        assert [c["value"] for c in response.data["choices"]] == ["light", "dark"]

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        with capture_logs() as logs:
            auth_client.post("/api/v1/catalog/attributes/", _TEXT_ATTRIBUTE, format="json")

        events = [entry for entry in logs if entry["event"] == "attribute_created"]
        # The audit trail records the stable user id, not the phone number (PII).
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_duplicate_code_returns_409(self, auth_client: APIClient) -> None:
        auth_client.post("/api/v1/catalog/attributes/", _TEXT_ATTRIBUTE, format="json")

        response = auth_client.post(
            "/api/v1/catalog/attributes/", _TEXT_ATTRIBUTE, format="json"
        )

        assert response.status_code == 409

    def test_invalid_code_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/",
            {"code": "Not A Slug", "name": "Origin", "input_type": "plain_text"},
            format="json",
        )

        assert response.status_code == 400

    def test_unknown_input_type_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/",
            {"code": "origin", "name": "Origin", "input_type": "rich_text"},
            format="json",
        )

        assert response.status_code == 400

    def test_dropdown_without_choices_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/",
            {"code": "roast-level", "name": "Roast", "input_type": "dropdown"},
            format="json",
        )

        assert response.status_code == 400

    def test_text_attribute_with_choices_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/",
            {
                "code": "origin",
                "name": "Origin",
                "input_type": "plain_text",
                "choices": [{"value": "x", "label": "X"}],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/attributes/", {"code": "origin"}, format="json"
        )

        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_attributes_sorted_by_code(self, auth_client: APIClient) -> None:
        auth_client.post("/api/v1/catalog/attributes/", _DROPDOWN_ATTRIBUTE, format="json")
        auth_client.post("/api/v1/catalog/attributes/", _TEXT_ATTRIBUTE, format="json")

        response = auth_client.get("/api/v1/catalog/attributes/")

        assert response.status_code == 200
        assert [a["code"] for a in response.data] == ["origin", "roast-level"]

    def test_retrieves_a_single_attribute(self, auth_client: APIClient) -> None:
        auth_client.post("/api/v1/catalog/attributes/", _DROPDOWN_ATTRIBUTE, format="json")

        response = auth_client.get("/api/v1/catalog/attributes/roast-level/")

        assert response.status_code == 200
        assert response.data["name"] == "Roast level"
        assert [c["label"] for c in response.data["choices"]] == ["Light", "Dark"]

    def test_unknown_attribute_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/attributes/ghost/").status_code == 404
