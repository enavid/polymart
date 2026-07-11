"""Integration tests for the tax-rate endpoint (real DRF stack)."""

from __future__ import annotations

import pytest
from pytest_django.fixtures import SettingsWrapper
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_URL = "/api/v1/tax/rate/"


class TestTaxRateEndpoint:
    @pytest.fixture(autouse=True)
    def _configure_rates(self, settings: SettingsWrapper) -> None:
        settings.TAX_RATES = {"ir-main": "9"}

    def test_reads_a_channels_rate_without_auth(self) -> None:
        # Public: the tax rate is channel configuration, not shopper data.
        response = APIClient().get(_URL, {"channel": "ir-main"})

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body == {"channel": "ir-main", "rate": "9"}

    def test_an_untaxed_channel_returns_a_null_rate(self) -> None:
        response = APIClient().get(_URL, {"channel": "ghost"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"channel": "ghost", "rate": None}

    def test_a_missing_channel_is_rejected(self) -> None:
        response = APIClient().get(_URL)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
