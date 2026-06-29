"""Integration tests for the variant stock endpoints (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_STOCK_URL = "/api/v1/catalog/variants/HB-250/stock/"


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


def _seed_variant(client: APIClient) -> None:
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
    assert (
        client.post(
            "/api/v1/catalog/products/house-blend/variants/",
            {"sku": "HB-250", "name": "House Blend 250g"},
            format="json",
        ).status_code
        == 201
    )


class TestSecurity:
    def test_reading_requires_authentication(self) -> None:
        assert APIClient().get(_STOCK_URL).status_code == 401

    def test_setting_requires_authentication(self) -> None:
        assert APIClient().put(_STOCK_URL, {"quantity": 1}, format="json").status_code == 401

    def test_adjusting_requires_authentication(self) -> None:
        assert APIClient().patch(_STOCK_URL, {"delta": 1}, format="json").status_code == 401

    def test_member_without_permission_cannot_set(
        self, auth_client: APIClient, member_client: APIClient
    ) -> None:
        _seed_variant(auth_client)
        assert (
            member_client.put(_STOCK_URL, {"quantity": 5}, format="json").status_code == 403
        )


class TestSet:
    def test_sets_the_quantity(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        response = auth_client.put(_STOCK_URL, {"quantity": 12}, format="json")

        assert response.status_code == 200
        assert response.data["quantity"] == 12

    def test_set_is_idempotent(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)
        auth_client.put(_STOCK_URL, {"quantity": 12}, format="json")

        response = auth_client.put(_STOCK_URL, {"quantity": 12}, format="json")

        assert response.status_code == 200
        assert response.data["quantity"] == 12

    def test_audit_records_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _seed_variant(auth_client)
        with capture_logs() as logs:
            auth_client.put(_STOCK_URL, {"quantity": 12}, format="json")

        events = [e for e in logs if e["event"] == "variant_stock_set"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_variant_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.put(
            "/api/v1/catalog/variants/GHOST/stock/", {"quantity": 1}, format="json"
        )

        assert response.status_code == 404

    def test_negative_quantity_returns_400(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        response = auth_client.put(_STOCK_URL, {"quantity": -1}, format="json")

        assert response.status_code == 400

    def test_non_integer_quantity_returns_400(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        response = auth_client.put(_STOCK_URL, {"quantity": "abc"}, format="json")

        assert response.status_code == 400

    def test_missing_quantity_returns_400(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        assert auth_client.put(_STOCK_URL, {}, format="json").status_code == 400


class TestAdjust:
    def test_a_positive_delta_increases_the_quantity(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)
        auth_client.put(_STOCK_URL, {"quantity": 10}, format="json")

        response = auth_client.patch(_STOCK_URL, {"delta": 5}, format="json")

        assert response.status_code == 200
        assert response.data["quantity"] == 15

    def test_a_negative_delta_decreases_the_quantity(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)
        auth_client.put(_STOCK_URL, {"quantity": 10}, format="json")

        response = auth_client.patch(_STOCK_URL, {"delta": -4}, format="json")

        assert response.status_code == 200
        assert response.data["quantity"] == 6

    def test_an_oversell_returns_400(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)
        auth_client.put(_STOCK_URL, {"quantity": 2}, format="json")

        response = auth_client.patch(_STOCK_URL, {"delta": -3}, format="json")

        assert response.status_code == 400
        assert auth_client.get(_STOCK_URL).data["quantity"] == 2

    def test_unknown_variant_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.patch(
            "/api/v1/catalog/variants/GHOST/stock/", {"delta": 1}, format="json"
        )

        assert response.status_code == 404

    def test_missing_delta_returns_400(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        assert auth_client.patch(_STOCK_URL, {}, format="json").status_code == 400


class TestGet:
    def test_reads_the_quantity(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)
        auth_client.put(_STOCK_URL, {"quantity": 7}, format="json")

        response = auth_client.get(_STOCK_URL)

        assert response.status_code == 200
        assert response.data["quantity"] == 7

    def test_defaults_to_zero_for_a_variant_without_stock(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        response = auth_client.get(_STOCK_URL)

        assert response.status_code == 200
        assert response.data["quantity"] == 0

    def test_unknown_variant_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/variants/GHOST/stock/").status_code == 404
