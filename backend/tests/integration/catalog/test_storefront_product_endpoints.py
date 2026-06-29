"""Integration tests for the public storefront catalog read API (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_LIST_URL = "/api/v1/catalog/storefront/products/"


@pytest.fixture
def admin_client() -> APIClient:
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    build_assign_role().execute(user_id=user.pk, role_name=CATALOG_ADMIN_ROLE)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _publish(client: APIClient, code: str) -> None:
    assert (
        client.put(
            f"/api/v1/catalog/products/{code}/publication/",
            {"is_published": True},
            format="json",
        ).status_code
        == 200
    )


def _seed(client: APIClient) -> None:
    for code, name in (("coffee", "Coffee"), ("tea", "Tea")):
        assert (
            client.post(
                "/api/v1/catalog/product-types/", {"code": code, "name": name}, format="json"
            ).status_code
            == 201
        )
    for code, name, ptype in (
        ("house-blend", "House Blend", "coffee"),
        ("espresso", "Espresso Roast", "coffee"),
        ("green-tea", "Green Tea", "tea"),
    ):
        assert (
            client.post(
                "/api/v1/catalog/products/",
                {"code": code, "name": name, "product_type": ptype},
                format="json",
            ).status_code
            == 201
        )
    # Build a category and a collection for filter tests.
    assert (
        client.post(
            "/api/v1/catalog/categories/", {"slug": "beverages", "name": "Beverages"}, format="json"
        ).status_code
        == 201
    )
    assert (
        client.put(
            "/api/v1/catalog/products/house-blend/categories/",
            {"categories": ["beverages"]},
            format="json",
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/catalog/collections/", {"slug": "featured", "name": "Featured"}, format="json"
        ).status_code
        == 201
    )
    assert (
        client.put(
            "/api/v1/catalog/collections/featured/products/",
            {"products": ["espresso"]},
            format="json",
        ).status_code
        == 200
    )
    # Publish the two coffees; green-tea stays a draft.
    _publish(client, "house-blend")
    _publish(client, "espresso")


class TestAccess:
    def test_listing_is_public(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        assert APIClient().get(_LIST_URL).status_code == 200

    def test_detail_is_public(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        assert APIClient().get(f"{_LIST_URL}house-blend/").status_code == 200


class TestList:
    def test_returns_only_published_products(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL)

        codes = {p["code"] for p in response.data["results"]}
        assert codes == {"house-blend", "espresso"}
        assert response.data["count"] == 2

    def test_does_not_leak_the_internal_id(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL)

        assert "id" not in response.data["results"][0]

    def test_filters_by_product_type(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL, {"product_type": "coffee"})

        assert {p["code"] for p in response.data["results"]} == {"house-blend", "espresso"}

    def test_filters_by_category(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL, {"category": "beverages"})

        assert [p["code"] for p in response.data["results"]] == ["house-blend"]

    def test_filters_by_collection(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL, {"collection": "featured"})

        assert [p["code"] for p in response.data["results"]] == ["espresso"]

    def test_search_matches_name(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL, {"search": "espresso"})

        assert [p["code"] for p in response.data["results"]] == ["espresso"]

    def test_a_draft_is_never_matched_by_search(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL, {"search": "green"})

        assert response.data["results"] == []

    def test_pagination_windows_results(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(_LIST_URL, {"limit": 1, "offset": 0})

        assert len(response.data["results"]) == 1
        assert response.data["count"] == 2
        assert response.data["limit"] == 1
        assert response.data["offset"] == 0

    def test_an_out_of_range_limit_is_rejected(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        assert APIClient().get(_LIST_URL, {"limit": 1000}).status_code == 400

    def test_a_non_integer_limit_is_rejected(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        assert APIClient().get(_LIST_URL, {"limit": "abc"}).status_code == 400


class TestDetail:
    def test_reads_a_published_product(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        response = APIClient().get(f"{_LIST_URL}house-blend/")

        assert response.status_code == 200
        assert response.data["code"] == "house-blend"
        assert "id" not in response.data

    def test_a_draft_returns_404(self, admin_client: APIClient) -> None:
        _seed(admin_client)

        assert APIClient().get(f"{_LIST_URL}green-tea/").status_code == 404

    def test_an_unknown_product_returns_404(self, admin_client: APIClient) -> None:
        assert APIClient().get(f"{_LIST_URL}ghost/").status_code == 404
