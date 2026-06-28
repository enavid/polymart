"""Integration tests for the channel HTTP endpoints (full request path + DB).

These assert the secure-by-default posture (auth required), the happy paths, and
the mapping of domain errors to HTTP status codes.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def auth_client() -> APIClient:
    user = get_user_model().objects.create_user(username="operator", password="pw")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestSecurity:
    def test_listing_requires_authentication(self) -> None:
        response = APIClient().get("/api/v1/channels/")

        assert response.status_code == 401

    def test_creating_requires_authentication(self) -> None:
        response = APIClient().post("/api/v1/channels/", {}, format="json")

        assert response.status_code == 401


class TestCreate:
    def test_creates_a_channel(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee Store", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["slug"] == "coffee"
        assert response.data["currency"] == "IRR"
        assert response.data["is_active"] is True
        assert response.data["id"] is not None

    def test_duplicate_slug_returns_409(self, auth_client: APIClient) -> None:
        body = {"slug": "coffee", "name": "Coffee", "currency": "IRR"}
        auth_client.post("/api/v1/channels/", body, format="json")

        response = auth_client.post("/api/v1/channels/", body, format="json")

        assert response.status_code == 409

    def test_invalid_currency_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "toman"},
            format="json",
        )

        assert response.status_code == 400

    def test_invalid_slug_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post(
            "/api/v1/channels/",
            {"slug": "Not A Slug", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        assert response.status_code == 400

    def test_missing_fields_returns_400(self, auth_client: APIClient) -> None:
        response = auth_client.post("/api/v1/channels/", {"slug": "coffee"}, format="json")

        assert response.status_code == 400


class TestListAndRetrieve:
    def test_lists_channels(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get("/api/v1/channels/")

        assert response.status_code == 200
        assert {c["slug"] for c in response.data} == {"coffee"}

    def test_can_filter_to_active_only(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {
                "slug": "draft",
                "name": "Draft",
                "currency": "IRR",
                "is_active": False,
            },
            format="json",
        )
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "live", "name": "Live", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get("/api/v1/channels/?active=true")

        assert {c["slug"] for c in response.data} == {"live"}

    def test_retrieves_a_single_channel(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = auth_client.get("/api/v1/channels/coffee/")

        assert response.status_code == 200
        assert response.data["name"] == "Coffee"

    def test_unknown_channel_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.get("/api/v1/channels/ghost/")

        assert response.status_code == 404


class TestStatusChange:
    def test_deactivates_a_channel(self, auth_client: APIClient) -> None:
        auth_client.post(
            "/api/v1/channels/",
            {"slug": "coffee", "name": "Coffee", "currency": "IRR"},
            format="json",
        )

        response = auth_client.patch(
            "/api/v1/channels/coffee/", {"is_active": False}, format="json"
        )

        assert response.status_code == 200
        assert response.data["is_active"] is False

    def test_status_change_on_unknown_channel_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.patch("/api/v1/channels/ghost/", {"is_active": False}, format="json")

        assert response.status_code == 404
