"""Integration tests for the public storefront taxonomy read endpoints.

These back the storefront's filter choosers (category / collection / product-type
dropdowns), so they must be readable by an anonymous visitor and must not leak the
internal database id.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CATEGORIES_URL = "/api/v1/catalog/storefront/categories/"
_COLLECTIONS_URL = "/api/v1/catalog/storefront/collections/"
_PRODUCT_TYPES_URL = "/api/v1/catalog/storefront/product-types/"


@pytest.fixture
def admin_client() -> APIClient:
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    build_assign_role().execute(user_id=user.pk, role_name=CATALOG_ADMIN_ROLE)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _seed(client: APIClient) -> None:
    assert (
        client.post(
            "/api/v1/catalog/categories/",
            {"slug": "hot-drinks", "name": "Hot Drinks"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/categories/",
            {"slug": "coffee-beans", "name": "Coffee Beans", "parent": "hot-drinks"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/collections/", {"slug": "featured", "name": "Featured"}, format="json"
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/product-types/", {"code": "coffee", "name": "Coffee"}, format="json"
        ).status_code
        == 201
    )


class TestStorefrontCategories:
    def test_is_public(self, admin_client: APIClient) -> None:
        _seed(admin_client)
        assert APIClient().get(_CATEGORIES_URL).status_code == 200

    def test_returns_the_tree_without_internal_id(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_CATEGORIES_URL)

        by_slug = {c["slug"]: c for c in response.data}
        assert by_slug["hot-drinks"]["parent"] is None
        assert by_slug["coffee-beans"]["parent"] == "hot-drinks"
        assert "id" not in by_slug["hot-drinks"]


class TestStorefrontCollections:
    def test_is_public_and_lists_collections(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_COLLECTIONS_URL)

        assert response.status_code == 200
        assert {c["slug"] for c in response.data} == {"featured"}
        assert "id" not in response.data[0]


class TestStorefrontProductTypes:
    def test_is_public_and_lists_product_types(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_PRODUCT_TYPES_URL)

        assert response.status_code == 200
        assert {t["code"] for t in response.data} == {"coffee"}
