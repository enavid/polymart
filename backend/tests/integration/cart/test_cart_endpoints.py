"""Integration tests for the cart endpoints (full path + DB).

The cart is resolved from the authenticated user, so these also assert the
security property that matters most here: one shopper can never reach another's
cart (no IDOR), because there is no cart id to tamper with.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.value_objects import ChannelPrice, ProductCode, ProductTypeCode
from src.domain.catalog.value_objects import Money as CatalogMoney
from src.domain.catalog.value_objects import Sku as CatalogSku
from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.channel.repositories import DjangoChannelRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"
_CART_URL = "/api/v1/cart/"
_ITEMS_URL = "/api/v1/cart/items/"


def _seed_channel(slug: str = _CHANNEL, currency: str = "IRR") -> None:
    DjangoChannelRepository().add(
        Channel(slug=ChannelSlug(slug), name="Iran", currency=Currency(currency))
    )


def _seed_variant(sku: str, amount: str | None) -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
        )
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=CatalogSku(sku), name="HB")
    )
    if amount is not None:
        DjangoVariantPriceRepository().replace(
            sku,
            (
                ChannelPrice(
                    channel=_CHANNEL, money=CatalogMoney(amount=Decimal(amount), currency="IRR")
                ),
            ),
        )


@pytest.fixture
def user() -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number="09120000001", password="pw")


@pytest.fixture
def client(user: AbstractBaseUser) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def other_client() -> APIClient:
    other = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
    api = APIClient()
    api.force_authenticate(user=other)
    return api


class TestSecurity:
    def test_reading_requires_authentication(self) -> None:
        assert APIClient().get(_CART_URL, {"channel": _CHANNEL}).status_code == 401

    def test_adding_requires_authentication(self) -> None:
        body = {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1}
        assert APIClient().post(_ITEMS_URL, body, format="json").status_code == 401

    def test_one_shopper_cannot_see_anothers_cart(
        self, client: APIClient, other_client: APIClient
    ) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")
        client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
        )

        # The other user, hitting the very same URL, gets their own (empty) cart.
        response = other_client.get(_CART_URL, {"channel": _CHANNEL})

        assert response.status_code == 200
        assert response.data["items"] == []
        assert response.data["total"] == "0"


class TestAdd:
    def test_adds_a_line_and_prices_the_cart(self, client: APIClient) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")

        response = client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
        )

        assert response.status_code == 200
        assert response.data["currency"] == "IRR"
        item = response.data["items"][0]
        assert item["sku"] == "HB-250"
        assert item["quantity"] == 2
        assert item["unit_price"] == "120000.0000"
        assert item["line_total"] == "240000.0000"
        assert response.data["total"] == "240000.0000"

    def test_adding_again_increments_the_quantity(self, client: APIClient) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")
        client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
        )

        response = client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 3}, format="json"
        )

        assert response.data["items"][0]["quantity"] == 5

    def test_unknown_variant_returns_404(self, client: APIClient) -> None:
        _seed_channel()

        response = client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "GHOST", "quantity": 1}, format="json"
        )

        assert response.status_code == 404

    def test_variant_without_a_price_in_the_channel_returns_400(self, client: APIClient) -> None:
        _seed_channel()
        _seed_variant("HB-250", None)  # exists but has no price

        response = client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1}, format="json"
        )

        assert response.status_code == 400

    def test_unknown_channel_returns_400(self, client: APIClient) -> None:
        response = client.post(
            _ITEMS_URL, {"channel": "nope", "sku": "HB-250", "quantity": 1}, format="json"
        )

        assert response.status_code == 400

    def test_non_positive_quantity_returns_400(self, client: APIClient) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")

        response = client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 0}, format="json"
        )

        assert response.status_code == 400

    def test_logs_the_owner_but_never_the_price(self, client: APIClient, user) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")

        with capture_logs() as logs:
            client.post(
                _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
            )

        event = next(e for e in logs if e["event"] == "cart_item_added")
        assert event["owner"] == str(user.pk)
        assert not any("amount" in key or "price" in key or "total" in key for key in event)


class TestGet:
    def test_empty_cart_totals_zero(self, client: APIClient) -> None:
        _seed_channel()

        response = client.get(_CART_URL, {"channel": _CHANNEL})

        assert response.status_code == 200
        assert response.data["items"] == []
        assert response.data["total"] == "0"

    def test_missing_channel_returns_400(self, client: APIClient) -> None:
        assert client.get(_CART_URL).status_code == 400

    def test_unknown_channel_returns_400(self, client: APIClient) -> None:
        assert client.get(_CART_URL, {"channel": "nope"}).status_code == 400

    def test_a_line_that_loses_its_price_is_unavailable_and_excluded(
        self, client: APIClient
    ) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")
        client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
        )
        # The channel price is withdrawn after the item is already in the cart.
        DjangoVariantPriceRepository().replace("HB-250", ())

        response = client.get(_CART_URL, {"channel": _CHANNEL})

        item = response.data["items"][0]
        assert item["available"] is False
        assert item["unit_price"] is None
        assert item["line_total"] is None
        assert response.data["total"] == "0"


class TestUpdate:
    def test_sets_the_quantity(self, client: APIClient) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")
        client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
        )

        response = client.put(
            f"{_ITEMS_URL}HB-250/", {"channel": _CHANNEL, "quantity": 5}, format="json"
        )

        assert response.status_code == 200
        assert response.data["items"][0]["quantity"] == 5

    def test_unknown_line_returns_404(self, client: APIClient) -> None:
        _seed_channel()

        response = client.put(
            f"{_ITEMS_URL}HB-250/", {"channel": _CHANNEL, "quantity": 5}, format="json"
        )

        assert response.status_code == 404

    def test_unknown_channel_returns_400(self, client: APIClient) -> None:
        response = client.put(
            f"{_ITEMS_URL}HB-250/", {"channel": "nope", "quantity": 5}, format="json"
        )

        assert response.status_code == 400


class TestRemove:
    def test_removes_the_line(self, client: APIClient) -> None:
        _seed_channel()
        _seed_variant("HB-250", "120000.00")
        client.post(
            _ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 2}, format="json"
        )

        response = client.delete(f"{_ITEMS_URL}HB-250/?channel={_CHANNEL}")

        assert response.status_code == 200
        assert response.data["items"] == []

    def test_unknown_line_returns_404(self, client: APIClient) -> None:
        _seed_channel()

        response = client.delete(f"{_ITEMS_URL}HB-250/?channel={_CHANNEL}")

        assert response.status_code == 404

    def test_unknown_channel_returns_400(self, client: APIClient) -> None:
        response = client.delete(f"{_ITEMS_URL}HB-250/?channel=nope")

        assert response.status_code == 400
