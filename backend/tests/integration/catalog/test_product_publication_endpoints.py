"""Integration tests for the admin product-publication endpoint (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_PUBLICATION_URL = "/api/v1/catalog/products/house-blend/publication/"


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


def _seed_product(client: APIClient) -> None:
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


class TestSecurity:
    def test_requires_authentication(self) -> None:
        assert (
            APIClient().put(_PUBLICATION_URL, {"is_published": True}, format="json").status_code
            == 401
        )

    def test_member_without_permission_cannot_publish(
        self, auth_client: APIClient, member_client: APIClient
    ) -> None:
        _seed_product(auth_client)
        assert (
            member_client.put(
                _PUBLICATION_URL, {"is_published": True}, format="json"
            ).status_code
            == 403
        )


class TestPublish:
    def test_a_new_product_is_unpublished_by_default(self, auth_client: APIClient) -> None:
        _seed_product(auth_client)

        response = auth_client.get("/api/v1/catalog/products/house-blend/")

        assert response.data["is_published"] is False

    def test_publishes_a_product(self, auth_client: APIClient) -> None:
        _seed_product(auth_client)

        response = auth_client.put(_PUBLICATION_URL, {"is_published": True}, format="json")

        assert response.status_code == 200
        assert response.data["is_published"] is True

    def test_unpublishes_a_product(self, auth_client: APIClient) -> None:
        _seed_product(auth_client)
        auth_client.put(_PUBLICATION_URL, {"is_published": True}, format="json")

        response = auth_client.put(_PUBLICATION_URL, {"is_published": False}, format="json")

        assert response.status_code == 200
        assert response.data["is_published"] is False

    def test_audit_records_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _seed_product(auth_client)
        with capture_logs() as logs:
            auth_client.put(_PUBLICATION_URL, {"is_published": True}, format="json")

        events = [e for e in logs if e["event"] == "product_publish_changed"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_product_returns_404(self, auth_client: APIClient) -> None:
        response = auth_client.put(
            "/api/v1/catalog/products/ghost/publication/", {"is_published": True}, format="json"
        )

        assert response.status_code == 404

    def test_missing_flag_returns_400(self, auth_client: APIClient) -> None:
        _seed_product(auth_client)

        assert auth_client.put(_PUBLICATION_URL, {}, format="json").status_code == 400
