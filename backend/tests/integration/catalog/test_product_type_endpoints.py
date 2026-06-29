"""Integration tests for the product-type endpoints (full path + DB)."""

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


def _create_attribute(client: APIClient, code: str) -> None:
    response = client.post(
        "/api/v1/catalog/attributes/",
        {"code": code, "name": code.title(), "input_type": "plain_text"},
        format="json",
    )
    assert response.status_code == 201


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        assert APIClient().get("/api/v1/catalog/product-types/").status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post("/api/v1/catalog/product-types/", {}, format="json")
        assert response.status_code == 401

    def test_member_without_permission_cannot_create(self, member_client: APIClient) -> None:
        response = member_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee"},
            format="json",
        )
        assert response.status_code == 403


class TestCreate:
    def test_creates_a_product_type_with_attributes_in_order(self, auth_client: APIClient) -> None:
        _create_attribute(auth_client, "roast-level")
        _create_attribute(auth_client, "origin")

        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "attributes": ["roast-level", "origin"]},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["code"] == "coffee"
        assert response.data["attributes"] == ["roast-level", "origin"]
        assert response.data["id"] is not None

    def test_creates_a_type_with_no_attributes(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "misc", "name": "Misc"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["attributes"] == []
        assert response.data["variant_attributes"] == []

    def test_creates_a_type_with_variant_attributes_in_order(self, auth_client: APIClient) -> None:
        _create_attribute(auth_client, "origin")
        _create_attribute(auth_client, "weight")
        _create_attribute(auth_client, "grind")

        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {
                "code": "coffee",
                "name": "Coffee",
                "attributes": ["origin"],
                "variant_attributes": ["weight", "grind"],
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["attributes"] == ["origin"]
        assert response.data["variant_attributes"] == ["weight", "grind"]

    def test_attribute_on_both_levels_returns_400(self, auth_client: APIClient) -> None:
        _create_attribute(auth_client, "origin")

        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {
                "code": "coffee",
                "name": "Coffee",
                "attributes": ["origin"],
                "variant_attributes": ["origin"],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_unknown_variant_attribute_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "variant_attributes": ["ghost"]},
            format="json",
        )

        assert response.status_code == 400

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        with capture_logs() as logs:
            auth_client.post(
                "/api/v1/catalog/product-types/",
                {"code": "coffee", "name": "Coffee"},
                format="json",
            )

        events = [e for e in logs if e["event"] == "product_type_created"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_attribute_reference_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "attributes": ["ghost"]},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_attribute_reference_returns_400(self, auth_client: APIClient) -> None:
        _create_attribute(auth_client, "origin")

        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "attributes": ["origin", "origin"]},
            format="json",
        )

        assert response.status_code == 400

    def test_invalid_code_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "Not A Slug", "name": "Coffee"},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_code_returns_409(self, auth_client: APIClient) -> None:
        body = {"code": "coffee", "name": "Coffee"}
        auth_client.post("/api/v1/catalog/product-types/", body, format="json")

        response = auth_client.post("/api/v1/catalog/product-types/", body, format="json")

        assert response.status_code == 409

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/product-types/", {"code": "coffee"}, format="json"
        )

        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_types_sorted_by_code(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/catalog/product-types/", {"code": "tea", "name": "Tea"}, format="json"
        )
        auth_client.post(
            "/api/v1/catalog/product-types/", {"code": "coffee", "name": "Coffee"}, format="json"
        )

        response = auth_client.get("/api/v1/catalog/product-types/")

        assert response.status_code == 200
        assert [t["code"] for t in response.data] == ["coffee", "tea"]

    def test_retrieves_a_single_type(self, auth_client: APIClient) -> None:
        _create_attribute(auth_client, "origin")
        auth_client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "attributes": ["origin"]},
            format="json",
        )

        response = auth_client.get("/api/v1/catalog/product-types/coffee/")

        assert response.status_code == 200
        assert response.data["name"] == "Coffee"
        assert response.data["attributes"] == ["origin"]

    def test_unknown_type_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/product-types/ghost/").status_code == 404
