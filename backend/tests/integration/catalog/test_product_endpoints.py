"""Integration tests for the product endpoints (full path + DB)."""

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


def _create_attribute(
    client: APIClient, code: str, *, input_type: str = "plain_text", required: bool = False
) -> None:
    response = client.post(
        "/api/v1/catalog/attributes/",
        {"code": code, "name": code.title(), "input_type": input_type, "required": required},
        format="json",
    )
    assert response.status_code == 201


def _create_coffee_type(client: APIClient) -> None:
    """A 'coffee' product type with a free-text origin and a required number weight."""
    _create_attribute(client, "origin")
    _create_attribute(client, "weight", input_type="number", required=True)
    response = client.post(
        "/api/v1/catalog/product-types/",
        {"code": "coffee", "name": "Coffee", "attributes": ["origin", "weight"]},
        format="json",
    )
    assert response.status_code == 201


def _product_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "code": "house-blend",
        "name": "House Blend",
        "product_type": "coffee",
        "values": [
            {"attribute": "origin", "value": "ethiopia"},
            {"attribute": "weight", "value": "250.50"},
        ],
    }
    body.update(overrides)
    return body


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        assert APIClient().get("/api/v1/catalog/products/").status_code == 401

    def test_creating_requires_authentication(self) -> None:
        assert APIClient().post("/api/v1/catalog/products/", {}, format="json").status_code == 401

    def test_member_without_permission_cannot_create(self, member_client: APIClient) -> None:
        response = member_client.post("/api/v1/catalog/products/", _product_body(), format="json")
        assert response.status_code == 403


class TestCreate:
    def test_creates_a_conforming_product(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/",
            _product_body(metadata={"supplier": "ACME"}),
            format="json",
        )

        assert response.status_code == 201
        assert response.data["code"] == "house-blend"
        assert response.data["id"] is not None
        values = {v["attribute"]: v["value"] for v in response.data["values"]}
        # The weight is canonicalized through Decimal, preserving the trailing zero.
        assert values == {"origin": "ethiopia", "weight": "250.50"}
        assert response.data["metadata"] == {"supplier": "ACME"}

    def test_audit_event_records_the_authenticated_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _create_coffee_type(auth_client)
        with capture_logs() as logs:
            auth_client.post("/api/v1/catalog/products/", _product_body(), format="json")

        events = [e for e in logs if e["event"] == "product_created"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_missing_required_attribute_returns_400(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/",
            _product_body(values=[{"attribute": "origin", "value": "ethiopia"}]),
            format="json",
        )

        assert response.status_code == 400

    def test_value_for_unassigned_attribute_returns_400(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)
        _create_attribute(auth_client, "color")

        response = auth_client.post(
            "/api/v1/catalog/products/",
            _product_body(
                values=[
                    {"attribute": "origin", "value": "ethiopia"},
                    {"attribute": "weight", "value": "250"},
                    {"attribute": "color", "value": "brown"},
                ]
            ),
            format="json",
        )

        assert response.status_code == 400

    def test_malformed_number_value_returns_400(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/",
            _product_body(
                values=[
                    {"attribute": "origin", "value": "ethiopia"},
                    {"attribute": "weight", "value": "heavy"},
                ]
            ),
            format="json",
        )

        assert response.status_code == 400

    def test_unknown_product_type_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/products/",
            {"code": "house-blend", "name": "House Blend", "product_type": "ghost"},
            format="json",
        )

        assert response.status_code == 400

    def test_invalid_code_returns_400(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)

        response = auth_client.post(
            "/api/v1/catalog/products/", _product_body(code="Not A Slug"), format="json"
        )

        assert response.status_code == 400

    def test_duplicate_code_returns_409(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)
        auth_client.post("/api/v1/catalog/products/", _product_body(), format="json")

        response = auth_client.post("/api/v1/catalog/products/", _product_body(), format="json")

        assert response.status_code == 409

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/catalog/products/", {"code": "house-blend"}, format="json"
        )

        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_products_sorted_by_code(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)
        auth_client.post(
            "/api/v1/catalog/products/", _product_body(code="tea-blend"), format="json"
        )
        auth_client.post(
            "/api/v1/catalog/products/", _product_body(code="house-blend"), format="json"
        )

        response = auth_client.get("/api/v1/catalog/products/")

        assert response.status_code == 200
        assert [p["code"] for p in response.data] == ["house-blend", "tea-blend"]

    def test_retrieves_a_single_product(self, auth_client: APIClient) -> None:
        _create_coffee_type(auth_client)
        auth_client.post("/api/v1/catalog/products/", _product_body(), format="json")

        response = auth_client.get("/api/v1/catalog/products/house-blend/")

        assert response.status_code == 200
        assert response.data["name"] == "House Blend"
        assert response.data["product_type"] == "coffee"

    def test_unknown_product_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/products/ghost/").status_code == 404
