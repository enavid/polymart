"""Integration tests for the product-category endpoints (full path + DB)."""

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


def _seed(client: APIClient) -> None:
    assert (
        client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/products/",
            {"code": "house-blend", "name": "House Blend", "product_type": "coffee"},
            format="json",
        ).status_code
        == 201
    )
    for slug in ("coffee", "espresso"):
        assert (
            client.post(
                "/api/v1/catalog/categories/",
                {"slug": slug, "name": slug.title()},
                format="json",
            ).status_code
            == 201
        )


class TestSecurity:
    def test_reading_requires_authentication(self) -> None:
        response = APIClient().get("/api/v1/catalog/products/house-blend/categories/")
        assert response.status_code == 401

    def test_setting_requires_authentication(self) -> None:
        response = APIClient().put(
            "/api/v1/catalog/products/house-blend/categories/", {}, format="json"
        )
        assert response.status_code == 401

    def test_member_without_permission_cannot_set(
        self, auth_client: APIClient, member_client: APIClient
    ) -> None:
        _seed(auth_client)
        response = member_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["coffee"]},
            format="json",
        )
        assert response.status_code == 403


class TestSet:
    def test_assigns_categories_to_a_product(self, auth_client: APIClient) -> None:
        _seed(auth_client)

        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["coffee", "espresso"]},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["categories"] == ["coffee", "espresso"]

    def test_set_is_idempotent(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        body = {"categories": ["coffee"]}
        auth_client.put("/api/v1/catalog/products/house-blend/categories/", body, format="json")

        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/", body, format="json"
        )

        assert response.status_code == 200
        assert response.data["categories"] == ["coffee"]

    def test_replacing_overwrites_membership(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["coffee", "espresso"]},
            format="json",
        )

        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["espresso"]},
            format="json",
        )

        assert response.data["categories"] == ["espresso"]

    def test_audit_records_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _seed(auth_client)
        with capture_logs() as logs:
            auth_client.put(
                "/api/v1/catalog/products/house-blend/categories/",
                {"categories": ["coffee"]},
                format="json",
            )

        events = [e for e in logs if e["event"] == "product_categories_set"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_product_returns_404(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            "/api/v1/catalog/products/ghost/categories/",
            {"categories": ["coffee"]},
            format="json",
        )

        assert response.status_code == 404

    def test_unknown_category_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["ghost"]},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_category_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["coffee", "coffee"]},
            format="json",
        )

        assert response.status_code == 400

    def test_malformed_category_slug_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["Not A Slug"]},
            format="json",
        )

        assert response.status_code == 400

    def test_missing_categories_field_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/", {}, format="json"
        )

        assert response.status_code == 400


class TestGet:
    def test_lists_a_products_categories(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        auth_client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["coffee", "espresso"]},
            format="json",
        )

        response = auth_client.get("/api/v1/catalog/products/house-blend/categories/")

        assert response.status_code == 200
        assert response.data["categories"] == ["coffee", "espresso"]

    def test_empty_for_a_product_without_categories(self, auth_client: APIClient) -> None:
        _seed(auth_client)

        response = auth_client.get("/api/v1/catalog/products/house-blend/categories/")

        assert response.status_code == 200
        assert response.data["categories"] == []

    def test_unknown_product_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.get("/api/v1/catalog/products/ghost/categories/")
        assert response.status_code == 404
