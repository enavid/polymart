"""Integration tests for the collection endpoints (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def admin_user() -> AbstractBaseUser:
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
    user = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        assert APIClient().get("/api/v1/catalog/collections/").status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post("/api/v1/catalog/collections/", {}, format="json")
        assert response.status_code == 401

    def test_member_without_permission_cannot_create(self, member_client: APIClient) -> None:
        response = member_client.post(
            "/api/v1/catalog/collections/",
            {"slug": "featured", "name": "Featured"},
            format="json",
        )
        assert response.status_code == 403


class TestCreate:
    def test_creates_a_collection(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/collections/",
            {"slug": "featured", "name": "Featured"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["id"] is not None
        assert response.data["slug"] == "featured"
        assert response.data["name"] == "Featured"

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        with capture_logs() as logs:
            auth_client.post(
                "/api/v1/catalog/collections/",
                {"slug": "featured", "name": "Featured"},
                format="json",
            )

        events = [e for e in logs if e["event"] == "collection_created"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_invalid_slug_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/collections/",
            {"slug": "Not A Slug", "name": "Featured"},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_slug_returns_409(self, auth_client: APIClient) -> None:
        body = {"slug": "featured", "name": "Featured"}
        auth_client.post("/api/v1/catalog/collections/", body, format="json")

        response = auth_client.post("/api/v1/catalog/collections/", body, format="json")

        assert response.status_code == 409

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post("/api/v1/catalog/collections/", {}, format="json")
        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_collections_sorted_by_slug(self, auth_client: APIClient) -> None:
        for slug in ("featured", "clearance"):
            auth_client.post(
                "/api/v1/catalog/collections/",
                {"slug": slug, "name": slug.title()},
                format="json",
            )

        response = auth_client.get("/api/v1/catalog/collections/")

        assert response.status_code == 200
        assert [c["slug"] for c in response.data] == ["clearance", "featured"]

    def test_retrieves_a_single_collection(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/catalog/collections/",
            {"slug": "featured", "name": "Featured"},
            format="json",
        )

        response = auth_client.get("/api/v1/catalog/collections/featured/")

        assert response.status_code == 200
        assert response.data["name"] == "Featured"

    def test_unknown_collection_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/collections/ghost/").status_code == 404
