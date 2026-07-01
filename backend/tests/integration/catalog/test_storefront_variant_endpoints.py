"""Integration tests for the public storefront variant read API (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.infrastructure.channel.repositories import DjangoChannelRepository
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"


def _variants_url(code: str) -> str:
    return f"/api/v1/catalog/storefront/products/{code}/variants/"


@pytest.fixture
def admin_client() -> APIClient:
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    build_assign_role().execute(user_id=user.pk, role_name=CATALOG_ADMIN_ROLE)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _seed_channel() -> None:
    DjangoChannelRepository().add(
        Channel(slug=ChannelSlug(_CHANNEL), name="Iran", currency=Currency("IRR"))
    )


def _seed_product(client: APIClient, *, published: bool, priced: bool) -> None:
    assert (
        client.post(
            "/api/v1/catalog/product-types/", {"code": "coffee", "name": "Coffee"}, format="json"
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
    if priced:
        assert (
            client.put(
                "/api/v1/catalog/variants/HB-250/prices/",
                {"prices": [{"channel": _CHANNEL, "amount": "120000.00"}]},
                format="json",
            ).status_code
            == 200
        )
    if published:
        assert (
            client.put(
                "/api/v1/catalog/products/house-blend/publication/",
                {"is_published": True},
                format="json",
            ).status_code
            == 200
        )


class TestStorefrontVariants:
    def test_anonymous_shopper_sees_published_variants_with_price(
        self, admin_client: APIClient
    ) -> None:
        _seed_channel()
        _seed_product(admin_client, published=True, priced=True)

        response = APIClient().get(_variants_url("house-blend"), {"channel": _CHANNEL})

        assert response.status_code == 200
        assert response.data["channel"] == _CHANNEL
        variant = response.data["variants"][0]
        assert variant["sku"] == "HB-250"
        assert "id" not in variant  # the internal id is never exposed publicly
        assert variant["price"] == {"amount": "120000.0000", "currency": "IRR"}

    def test_variant_without_a_price_in_the_channel_has_null_price(
        self, admin_client: APIClient
    ) -> None:
        _seed_channel()
        _seed_product(admin_client, published=True, priced=False)

        response = APIClient().get(_variants_url("house-blend"), {"channel": _CHANNEL})

        assert response.status_code == 200
        assert response.data["variants"][0]["price"] is None

    def test_a_draft_product_is_a_404(self, admin_client: APIClient) -> None:
        _seed_channel()
        _seed_product(admin_client, published=False, priced=True)

        response = APIClient().get(_variants_url("house-blend"), {"channel": _CHANNEL})

        assert response.status_code == 404

    def test_an_unknown_product_is_a_404(self) -> None:
        response = APIClient().get(_variants_url("ghost"), {"channel": _CHANNEL})

        assert response.status_code == 404

    def test_missing_channel_is_a_400(self, admin_client: APIClient) -> None:
        _seed_channel()
        _seed_product(admin_client, published=True, priced=True)

        response = APIClient().get(_variants_url("house-blend"))

        assert response.status_code == 400
