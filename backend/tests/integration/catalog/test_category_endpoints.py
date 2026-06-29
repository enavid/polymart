"""Integration tests for the category endpoints (full path + DB)."""

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
        assert APIClient().get("/api/v1/catalog/categories/").status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post("/api/v1/catalog/categories/", {}, format="json")
        assert response.status_code == 401

    def test_member_without_permission_cannot_create(self, member_client: APIClient) -> None:
        response = member_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "coffee", "name": "Coffee"},
            format="json",
        )
        assert response.status_code == 403


class TestCreate:
    def test_creates_a_root_category(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "coffee", "name": "Coffee"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["id"] is not None
        assert response.data["slug"] == "coffee"
        assert response.data["parent"] is None

    def test_creates_a_child_category(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "coffee", "name": "Coffee"},
            format="json",
        )

        response = auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "espresso", "name": "Espresso", "parent": "coffee"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["parent"] == "coffee"

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        with capture_logs() as logs:
            auth_client.post(
                "/api/v1/catalog/categories/",
                {"slug": "coffee", "name": "Coffee"},
                format="json",
            )

        events = [e for e in logs if e["event"] == "category_created"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_parent_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "espresso", "name": "Espresso", "parent": "ghost"},
            format="json",
        )

        assert response.status_code == 400

    def test_self_parenting_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "coffee", "name": "Coffee", "parent": "coffee"},
            format="json",
        )

        assert response.status_code == 400

    def test_invalid_slug_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "Not A Slug", "name": "Coffee"},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_slug_returns_409(self, auth_client: APIClient) -> None:
        body = {"slug": "coffee", "name": "Coffee"}
        auth_client.post("/api/v1/catalog/categories/", body, format="json")

        response = auth_client.post("/api/v1/catalog/categories/", body, format="json")

        assert response.status_code == 409

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post("/api/v1/catalog/categories/", {}, format="json")
        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_categories_sorted_by_slug(self, auth_client: APIClient) -> None:
        for slug in ("tea", "coffee"):
            auth_client.post(
                "/api/v1/catalog/categories/",
                {"slug": slug, "name": slug.title()},
                format="json",
            )

        response = auth_client.get("/api/v1/catalog/categories/")

        assert response.status_code == 200
        assert [c["slug"] for c in response.data] == ["coffee", "tea"]

    def test_retrieves_a_single_category(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/catalog/categories/",
            {"slug": "coffee", "name": "Coffee"},
            format="json",
        )

        response = auth_client.get("/api/v1/catalog/categories/coffee/")

        assert response.status_code == 200
        assert response.data["name"] == "Coffee"

    def test_unknown_category_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/categories/ghost/").status_code == 404
