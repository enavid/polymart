"""Integration tests for the variant endpoints (full path + DB)."""

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


def _create_product(client: APIClient, code: str = "house-blend") -> None:
    response = client.post(
        "/api/v1/catalog/product-types/",
        {"code": "coffee", "name": "Coffee", "attributes": []},
        format="json",
    )
    assert response.status_code in (201, 409)
    response = client.post(
        "/api/v1/catalog/products/",
        {"code": code, "name": code.title(), "product_type": "coffee"},
        format="json",
    )
    assert response.status_code == 201


def _create_product_with_options(client: APIClient, code: str = "house-blend") -> None:
    """Create a coffee type whose variant-level attribute is a required 'weight'."""
    assert (
        client.post(
            "/api/v1/catalog/attributes/",
            {"code": "weight", "name": "Weight", "input_type": "number", "required": True},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "variant_attributes": ["weight"]},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/products/",
            {"code": code, "name": code.title(), "product_type": "coffee"},
            format="json",
        ).status_code
        == 201
    )


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        response = APIClient().get("/api/v1/catalog/products/house-blend/variants/")
        assert response.status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post(
            "/api/v1/catalog/products/house-blend/variants/", {}, format="json"
        )
        assert response.status_code == 401

    def test_member_without_permission_cannot_create(
        self, auth_client: APIClient, member_client: APIClient
    ) -> None:
        _create_product(auth_client)
        response = member_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {"sku": "coffee-250", "name": "250g Bag"},
            format="json",
        )
        assert response.status_code == 403


class TestCreate:
    def test_creates_a_variant_with_canonical_sku(self, auth_client: APIClient) -> None:
        _create_product(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {"sku": "coffee-250", "name": "250g Bag"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["id"] is not None
        assert response.data["sku"] == "COFFEE-250"
        assert response.data["product"] == "house-blend"
        assert response.data["name"] == "250g Bag"

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _create_product(auth_client)
        with capture_logs() as logs:
            auth_client.post(
                "/api/v1/catalog/products/house-blend/variants/",
                {"sku": "coffee-250", "name": "250g Bag"},
                format="json",
            )

        events = [e for e in logs if e["event"] == "variant_created"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_creating_for_an_unknown_product_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/products/ghost/variants/",
            {"sku": "coffee-250", "name": "250g Bag"},
            format="json",
        )

        assert response.status_code == 404

    def test_invalid_sku_returns_400(self, auth_client: APIClient) -> None:
        _create_product(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {"sku": "not a sku", "name": "250g Bag"},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_sku_returns_409(self, auth_client: APIClient) -> None:
        _create_product(auth_client)
        body = {"sku": "coffee-250", "name": "250g Bag"}
        auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/", body, format="json"
        )

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/", body, format="json"
        )

        assert response.status_code == 409

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        _create_product(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/", {}, format="json"
        )

        assert response.status_code == 400


class TestOptionValues:
    def test_creates_a_variant_with_conforming_options(self, auth_client: APIClient) -> None:
        _create_product_with_options(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {
                "sku": "coffee-250",
                "name": "250g Bag",
                "values": [{"attribute": "weight", "value": "250"}],
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["values"] == [{"attribute": "weight", "value": "250"}]

    def test_missing_required_option_returns_400(self, auth_client: APIClient) -> None:
        _create_product_with_options(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {"sku": "coffee-250", "name": "250g Bag"},
            format="json",
        )

        assert response.status_code == 400

    def test_value_for_unassigned_attribute_returns_400(self, auth_client: APIClient) -> None:
        _create_product_with_options(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {
                "sku": "coffee-250",
                "name": "250g Bag",
                "values": [
                    {"attribute": "weight", "value": "250"},
                    {"attribute": "grind", "value": "espresso"},
                ],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_retrieve_includes_option_values(self, auth_client: APIClient) -> None:
        _create_product_with_options(auth_client)
        auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {
                "sku": "coffee-250",
                "name": "250g Bag",
                "values": [{"attribute": "weight", "value": "250"}],
            },
            format="json",
        )

        response = auth_client.get("/api/v1/catalog/variants/COFFEE-250/")

        assert response.status_code == 200
        assert response.data["values"] == [{"attribute": "weight", "value": "250"}]


class TestMedia:
    def test_creates_a_variant_with_media(self, auth_client: APIClient) -> None:
        _create_product(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {
                "sku": "coffee-250",
                "name": "250g Bag",
                "media": [
                    {"url": "/media/front.jpg", "alt_text": "Front"},
                    {"url": "https://cdn.example.com/back.jpg"},
                ],
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["media"] == [
            {"url": "/media/front.jpg", "alt_text": "Front"},
            {"url": "https://cdn.example.com/back.jpg", "alt_text": ""},
        ]

    def test_malformed_media_url_returns_400(self, auth_client: APIClient) -> None:
        _create_product(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {
                "sku": "coffee-250",
                "name": "250g Bag",
                "media": [{"url": "ftp://nope/x.jpg"}],
            },
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_media_url_returns_400(self, auth_client: APIClient) -> None:
        _create_product(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {
                "sku": "coffee-250",
                "name": "250g Bag",
                "media": [{"url": "/media/a.jpg"}, {"url": "/media/a.jpg"}],
            },
            format="json",
        )

        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_variants_for_a_product_sorted_by_sku(self, auth_client: APIClient) -> None:
        _create_product(auth_client)
        for sku in ("coffee-1000", "coffee-250"):
            auth_client.post(
                "/api/v1/catalog/products/house-blend/variants/",
                {"sku": sku, "name": sku},
                format="json",
            )

        response = auth_client.get("/api/v1/catalog/products/house-blend/variants/")

        assert response.status_code == 200
        assert [v["sku"] for v in response.data] == ["COFFEE-1000", "COFFEE-250"]

    def test_listing_for_an_unknown_product_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/products/ghost/variants/").status_code == 404

    def test_retrieves_a_single_variant(self, auth_client: APIClient) -> None:
        _create_product(auth_client)
        auth_client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {"sku": "coffee-250", "name": "250g Bag"},
            format="json",
        )

        response = auth_client.get("/api/v1/catalog/variants/COFFEE-250/")

        assert response.status_code == 200
        assert response.data["name"] == "250g Bag"
        assert response.data["product"] == "house-blend"

    def test_unknown_variant_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/variants/GHOST/").status_code == 404
