"""Integration tests for the rule-based collection endpoints (full path + DB)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from src.domain.access.registry import CATALOG_ADMIN_ROLE
from src.interface.api.access.container import build_assign_role

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_RULE_URL = "/api/v1/catalog/collections/dark-roasts/rule/"
_MEMBERS_URL = "/api/v1/catalog/collections/dark-roasts/rule/members/"


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


def _seed(client: APIClient) -> None:
    assert (
        client.post(
            "/api/v1/catalog/collections/",
            {"slug": "dark-roasts", "name": "Dark Roasts"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/attributes/",
            {"code": "roast-level", "name": "Roast Level", "input_type": "plain_text"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/catalog/product-types/",
            {"code": "coffee", "name": "Coffee", "attributes": ["roast-level"]},
            format="json",
        ).status_code
        == 201
    )
    for code, roast in (("house-blend", "dark"), ("breakfast", "light")):
        assert (
            client.post(
                "/api/v1/catalog/products/",
                {
                    "code": code,
                    "name": code.title(),
                    "product_type": "coffee",
                    "values": [{"attribute": "roast-level", "value": roast}],
                },
                format="json",
            ).status_code
            == 201
        )


def _dark_rule() -> dict:
    return {"conditions": [{"attribute": "roast-level", "operator": "equals", "value": "dark"}]}


class TestSecurity:
    def test_reading_requires_authentication(self) -> None:
        assert APIClient().get(_RULE_URL).status_code == 401

    def test_setting_requires_authentication(self) -> None:
        assert APIClient().put(_RULE_URL, {}, format="json").status_code == 401

    def test_resolving_members_requires_authentication(self) -> None:
        assert APIClient().get(_MEMBERS_URL).status_code == 401

    def test_member_without_permission_cannot_set(
        self, auth_client: APIClient, member_client: APIClient
    ) -> None:
        _seed(auth_client)
        assert member_client.put(_RULE_URL, _dark_rule(), format="json").status_code == 403


class TestSet:
    def test_sets_a_rule(self, auth_client: APIClient) -> None:
        _seed(auth_client)

        response = auth_client.put(_RULE_URL, _dark_rule(), format="json")

        assert response.status_code == 200
        assert response.data["conditions"] == [
            {"attribute": "roast-level", "operator": "equals", "value": "dark"}
        ]

    def test_set_is_idempotent(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        auth_client.put(_RULE_URL, _dark_rule(), format="json")

        response = auth_client.put(_RULE_URL, _dark_rule(), format="json")

        assert response.status_code == 200
        assert len(response.data["conditions"]) == 1

    def test_replacing_with_an_empty_rule_clears_it(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        auth_client.put(_RULE_URL, _dark_rule(), format="json")

        response = auth_client.put(_RULE_URL, {"conditions": []}, format="json")

        assert response.status_code == 200
        assert response.data["conditions"] == []

    def test_audit_records_the_actor(
        self, auth_client: APIClient, admin_user: AbstractBaseUser
    ) -> None:
        _seed(auth_client)
        with capture_logs() as logs:
            auth_client.put(_RULE_URL, _dark_rule(), format="json")

        events = [e for e in logs if e["event"] == "collection_rule_set"]
        assert events and events[0]["actor"] == str(admin_user.pk)

    def test_unknown_collection_returns_404(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            "/api/v1/catalog/collections/ghost/rule/", _dark_rule(), format="json"
        )

        assert response.status_code == 404

    def test_unknown_attribute_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            _RULE_URL,
            {"conditions": [{"attribute": "ghost", "operator": "equals", "value": "x"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_unknown_operator_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        response = auth_client.put(
            _RULE_URL,
            {"conditions": [{"attribute": "roast-level", "operator": "contains", "value": "d"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_duplicate_condition_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        condition = {"attribute": "roast-level", "operator": "equals", "value": "dark"}
        response = auth_client.put(
            _RULE_URL, {"conditions": [condition, condition]}, format="json"
        )

        assert response.status_code == 400

    def test_missing_conditions_field_returns_400(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        assert auth_client.put(_RULE_URL, {}, format="json").status_code == 400


class TestGet:
    def test_reads_the_rule(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        auth_client.put(_RULE_URL, _dark_rule(), format="json")

        response = auth_client.get(_RULE_URL)

        assert response.status_code == 200
        assert response.data["conditions"] == [
            {"attribute": "roast-level", "operator": "equals", "value": "dark"}
        ]

    def test_empty_for_a_collection_without_a_rule(self, auth_client: APIClient) -> None:
        _seed(auth_client)

        response = auth_client.get(_RULE_URL)

        assert response.status_code == 200
        assert response.data["conditions"] == []

    def test_unknown_collection_returns_404(self, auth_client: APIClient) -> None:
        assert auth_client.get("/api/v1/catalog/collections/ghost/rule/").status_code == 404


class TestMembers:
    def test_resolves_matching_products(self, auth_client: APIClient) -> None:
        _seed(auth_client)
        auth_client.put(_RULE_URL, _dark_rule(), format="json")

        response = auth_client.get(_MEMBERS_URL)

        assert response.status_code == 200
        assert response.data["products"] == ["house-blend"]

    def test_empty_for_a_collection_without_a_rule(self, auth_client: APIClient) -> None:
        _seed(auth_client)

        response = auth_client.get(_MEMBERS_URL)

        assert response.status_code == 200
        assert response.data["products"] == []

    def test_unknown_collection_returns_404(self, auth_client: APIClient) -> None:
        assert (
            auth_client.get("/api/v1/catalog/collections/ghost/rule/members/").status_code == 404
        )
