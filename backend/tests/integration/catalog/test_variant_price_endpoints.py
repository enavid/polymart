"""Integration tests for the variant pricing endpoints (full path + DB)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.infrastructure.channel.models import ChannelModel
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_PRICES_URL = "/api/v1/catalog/variants/HB-250/prices/"


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


def _seed_channels() -> None:
    # Channels are created directly (the catalog admin role does not manage channels).
    ChannelModel.objects.create(slug="ir-toman", name="Iran", currency_code="IRR")
    ChannelModel.objects.create(slug="us-store", name="US", currency_code="USD")


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


def _ir_price() -> dict:
    return {"prices": [{"channel": "ir-toman", "amount": "1500"}]}


class TestSecurity:
    def test_reading_requires_authentication(self) -> None:
        assert APIClient().get(_PRICES_URL).status_code == 401

    def test_setting_requires_authentication(self) -> None:
        assert APIClient().put(_PRICES_URL, {}, format="json").status_code == 401

    def test_member_without_permission_cannot_set(
        self, auth_client: APIClient, member_client: APIClient
    ) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        assert member_client.put(_PRICES_URL, _ir_price(), format="json").status_code == 403


class TestSet:
    def test_sets_a_price_deriving_the_currency(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)

        response = auth_client.put(_PRICES_URL, _ir_price(), format="json")

        assert response.status_code == 200
        assert len(response.data["prices"]) == 1
        price = response.data["prices"][0]
        assert price["channel"] == "ir-toman"
        assert price["currency"] == "IRR"
        assert Decimal(price["amount"]) == Decimal("1500")

    def test_prices_two_channels_in_their_own_currencies(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)

        response = auth_client.put(
            _PRICES_URL,
            {
                "prices": [
                    {"channel": "us-store", "amount": "9.99"},
                    {"channel": "ir-toman", "amount": "1500"},
                ]
            },
            format="json",
        )

        assert response.status_code == 200
        by_channel = {p["channel"]: p["currency"] for p in response.data["prices"]}
        assert by_channel == {"ir-toman": "IRR", "us-store": "USD"}

    def test_set_is_idempotent(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        auth_client.put(_PRICES_URL, _ir_price(), format="json")

        response = auth_client.put(_PRICES_URL, _ir_price(), format="json")

        assert response.status_code == 200
        assert len(response.data["prices"]) == 1

    def test_replacing_with_an_empty_set_clears_it(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        auth_client.put(_PRICES_URL, _ir_price(), format="json")

        response = auth_client.put(_PRICES_URL, {"prices": []}, format="json")

        assert response.status_code == 200
        assert response.data["prices"] == []

    def test_audit_records_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        with capture_logs() as logs:
            auth_client.put(_PRICES_URL, _ir_price(), format="json")

        events = [e for e in logs if e["event"] == "variant_prices_set"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_variant_returns_404(self, auth_client: APIClient) -> None:
        _seed_channels()
        response = auth_client.put(
            "/api/v1/catalog/variants/GHOST/prices/", _ir_price(), format="json"
        )

        assert response.status_code == 404

    def test_unknown_channel_returns_400(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        response = auth_client.put(
            _PRICES_URL,
            {"prices": [{"channel": "ghost", "amount": "1500"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_negative_amount_returns_400(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        response = auth_client.put(
            _PRICES_URL,
            {"prices": [{"channel": "ir-toman", "amount": "-1"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_zero_amount_returns_400(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        response = auth_client.put(
            _PRICES_URL,
            {"prices": [{"channel": "ir-toman", "amount": "0"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_too_many_decimal_places_returns_400(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        response = auth_client.put(
            _PRICES_URL,
            {"prices": [{"channel": "ir-toman", "amount": "1.23456"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_channel_returns_400(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        response = auth_client.put(
            _PRICES_URL,
            {
                "prices": [
                    {"channel": "ir-toman", "amount": "1500"},
                    {"channel": "ir-toman", "amount": "1600"},
                ]
            },
            format="json",
        )

        assert response.status_code == 400

    def test_missing_prices_field_returns_400(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)
        assert auth_client.put(_PRICES_URL, {}, format="json").status_code == 400


class TestGet:
    def test_reads_the_prices(self, auth_client: APIClient) -> None:
        _seed_channels()
        _seed_variant(auth_client)
        auth_client.put(_PRICES_URL, _ir_price(), format="json")

        response = auth_client.get(_PRICES_URL)

        assert response.status_code == 200
        assert len(response.data["prices"]) == 1
        assert response.data["prices"][0]["currency"] == "IRR"

    def test_empty_for_a_variant_without_prices(self, auth_client: APIClient) -> None:
        _seed_variant(auth_client)

        response = auth_client.get(_PRICES_URL)

        assert response.status_code == 200
        assert response.data["prices"] == []

    def test_unknown_variant_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/variants/GHOST/prices/").status_code == 404
