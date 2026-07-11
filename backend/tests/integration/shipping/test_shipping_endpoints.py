"""Integration tests for the shipping methods endpoint (real DRF stack)."""

from __future__ import annotations

import pytest
from pytest_django.fixtures import SettingsWrapper
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_METHODS = {
    "ir-main": [
        {
            "code": "standard",
            "name": "Standard post",
            "price": "50000",
            "currency": "IRR",
            "min_days": 3,
            "max_days": 5,
        },
        {
            "code": "express",
            "name": "Express courier",
            "price": "120000",
            "currency": "IRR",
            "min_days": 1,
            "max_days": 2,
        },
    ],
}

_URL = "/api/v1/shipping/methods/"


class TestShippingMethodsEndpoint:
    @pytest.fixture(autouse=True)
    def _configure_methods(self, settings: SettingsWrapper) -> None:
        settings.SHIPPING_METHODS = _METHODS

    def test_lists_a_channels_methods_without_auth(self) -> None:
        # Public: shipping methods are channel configuration, not shopper data.
        response = APIClient().get(_URL, {"channel": "ir-main"})

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["channel"] == "ir-main"
        codes = [m["code"] for m in body["methods"]]
        assert codes == ["standard", "express"]

    def test_projects_price_as_an_exact_string(self) -> None:
        response = APIClient().get(_URL, {"channel": "ir-main"})
        standard = response.json()["methods"][0]
        assert standard["price"] == "50000"
        assert standard["currency"] == "IRR"
        assert standard["min_days"] == 3
        assert standard["max_days"] == 5

    def test_an_unconfigured_channel_returns_an_empty_list(self) -> None:
        response = APIClient().get(_URL, {"channel": "ghost"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["methods"] == []

    def test_a_missing_channel_is_a_400(self) -> None:
        response = APIClient().get(_URL)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


_ZONED = {
    "ir-main": [
        {
            "code": "standard",
            "name": "Standard post",
            "price": "50000",
            "currency": "IRR",
            "min_days": 3,
            "max_days": 5,
            "zone_rates": {"tehran": "30000"},
        },
    ],
}
_ZONES = {"ir-main": [{"code": "tehran", "name": "Tehran", "provinces": ["تهران"]}]}


class TestShippingMethodsZonedEndpoint:
    @pytest.fixture(autouse=True)
    def _configure(self, settings: SettingsWrapper) -> None:
        settings.SHIPPING_METHODS = _ZONED
        settings.SHIPPING_ZONES = _ZONES

    def test_a_province_in_a_zone_gets_the_zone_rate(self) -> None:
        response = APIClient().get(_URL, {"channel": "ir-main", "province": "تهران"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["methods"][0]["price"] == "30000"

    def test_a_province_outside_every_zone_gets_the_default_rate(self) -> None:
        response = APIClient().get(_URL, {"channel": "ir-main", "province": "اصفهان"})
        assert response.json()["methods"][0]["price"] == "50000"

    def test_no_province_lists_the_default_rate(self) -> None:
        response = APIClient().get(_URL, {"channel": "ir-main"})
        assert response.json()["methods"][0]["price"] == "50000"

    def test_a_blank_province_lists_the_default_rate(self) -> None:
        response = APIClient().get(_URL, {"channel": "ir-main", "province": "  "})
        assert response.json()["methods"][0]["price"] == "50000"

    def test_an_overlong_province_degrades_to_default_rates_not_a_400(self) -> None:
        response = APIClient().get(_URL, {"channel": "ir-main", "province": "x" * 200})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["methods"][0]["price"] == "50000"
