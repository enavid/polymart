"""Integration tests for the inventory admin HTTP endpoints (full request path + DB).

Cover the secure-by-default posture (auth required), two-layer RBAC on writes
(``manage_stock_source`` globally *or* per-source guardian scope), the happy paths for
listing/creating sources and setting/adjusting a variant's on-hand at a source, and the
mapping of domain errors to HTTP status codes (404 unknown source/variant, 409 oversell /
duplicate source, 400 malformed input).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient

from src.domain.access.registry import INVENTORY_ADMIN_ROLE
from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.value_objects import (
    ChannelPrice,
    ProductCode,
    ProductTypeCode,
    StockQuantity,
)
from src.domain.catalog.value_objects import Money as CatalogMoney
from src.domain.catalog.value_objects import Sku as CatalogSku
from src.domain.inventory.value_objects import StockSourceCode
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.inventory.models import StockSourceModel
from src.infrastructure.inventory.repositories import DjangoStockLevelRepository
from src.interface.api.access.container import (
    build_assign_role,
    build_grant_stock_source_management,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_SOURCES_URL = "/api/v1/inventory/sources/"


def _stock_url(code: str, sku: str) -> str:
    return f"{_SOURCES_URL}{code}/stock/{sku}/"


def _policy_url(sku: str) -> str:
    return f"/api/v1/inventory/policies/{sku}/"


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _client(user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _seed_variant(sku: str = "HB-250", *, stock: int = 5) -> None:
    """Create the minimal catalog rows so a variant exists with on-hand stock (main)."""
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="C"))
    DjangoProductRepository().add(
        Product(code=ProductCode("house-blend"), name="H", product_type=ProductTypeCode("coffee"))
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=CatalogSku(sku), name="v")
    )
    DjangoVariantPriceRepository().replace(
        sku,
        (ChannelPrice(channel="ir-main", money=CatalogMoney(amount=Decimal("1"), currency="IRR")),),
    )
    DjangoStockRepository().set_quantity(sku, StockQuantity(stock))


@pytest.fixture
def admin_client() -> APIClient:
    """A global inventory admin: may manage every source."""
    user = _user("09120000001")
    build_assign_role().execute(user_id=user.pk, role_name=INVENTORY_ADMIN_ROLE)
    return _client(user)


@pytest.fixture
def member_client() -> APIClient:
    """A plain authenticated user: may read but not mutate."""
    return _client(_user("09120000002"))


class TestSecurity:
    def test_all_verbs_require_authentication(self) -> None:
        anon = APIClient()
        assert anon.get(_SOURCES_URL).status_code == 401
        assert anon.post(_SOURCES_URL, {}, format="json").status_code == 401
        assert anon.get(_stock_url("main", "HB-250")).status_code == 401
        put = anon.put(_stock_url("main", "HB-250"), {"quantity": 1}, format="json")
        assert put.status_code == 401


class TestSourceListCreate:
    def test_member_can_list_but_not_create(self, member_client: APIClient) -> None:
        assert member_client.get(_SOURCES_URL).status_code == 200
        created = member_client.post(_SOURCES_URL, {"code": "north", "name": "N"}, format="json")
        assert created.status_code == 403

    def test_admin_creates_and_lists_sources(self, admin_client: APIClient) -> None:
        response = admin_client.post(
            _SOURCES_URL, {"code": "north", "name": "North Warehouse"}, format="json"
        )
        assert response.status_code == 201
        assert response.data["code"] == "north"
        assert response.data["id"] is not None

        listed = admin_client.get(_SOURCES_URL)
        codes = {row["code"] for row in listed.data}
        assert {"main", "north"} <= codes  # "main" is the seeded default

    def test_duplicate_source_is_a_conflict(self, admin_client: APIClient) -> None:
        admin_client.post(_SOURCES_URL, {"code": "north", "name": "N"}, format="json")
        again = admin_client.post(_SOURCES_URL, {"code": "north", "name": "N2"}, format="json")
        assert again.status_code == 409

    def test_a_malformed_code_is_a_bad_request(self, admin_client: APIClient) -> None:
        response = admin_client.post(
            _SOURCES_URL, {"code": "Not Valid!", "name": "N"}, format="json"
        )
        assert response.status_code == 400


class TestSourceStock:
    def test_admin_sets_and_adjusts_on_hand(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)

        set_response = admin_client.put(
            _stock_url("main", "HB-250"), {"quantity": 20}, format="json"
        )
        assert set_response.status_code == 200
        assert set_response.data["on_hand"] == 20
        assert set_response.data["available"] == 20

        adjust_response = admin_client.patch(
            _stock_url("main", "HB-250"), {"delta": -5}, format="json"
        )
        assert adjust_response.status_code == 200
        assert adjust_response.data["on_hand"] == 15

    def test_reading_stock_reflects_reservations(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        DjangoStockLevelRepository().reserve("HB-250", 2)

        response = admin_client.get(_stock_url("main", "HB-250"))

        assert response.status_code == 200
        assert response.data["on_hand"] == 5
        assert response.data["reserved"] == 2
        assert response.data["available"] == 3

    def test_setting_below_reserved_is_a_conflict(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        DjangoStockLevelRepository().reserve("HB-250", 3)

        response = admin_client.put(_stock_url("main", "HB-250"), {"quantity": 2}, format="json")

        assert response.status_code == 409

    def test_over_withdrawing_is_a_conflict(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=3)

        response = admin_client.patch(_stock_url("main", "HB-250"), {"delta": -5}, format="json")

        assert response.status_code == 409

    def test_unknown_source_is_a_not_found(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        response = admin_client.put(_stock_url("ghost", "HB-250"), {"quantity": 1}, format="json")
        assert response.status_code == 404

    def test_unknown_variant_is_a_not_found(self, admin_client: APIClient) -> None:
        response = admin_client.put(_stock_url("main", "GHOST-1"), {"quantity": 1}, format="json")
        assert response.status_code == 404

    def test_reading_an_unknown_source_or_variant_is_a_not_found(
        self, admin_client: APIClient
    ) -> None:
        _seed_variant("HB-250", stock=5)
        assert admin_client.get(_stock_url("ghost", "HB-250")).status_code == 404
        assert admin_client.get(_stock_url("main", "GHOST-1")).status_code == 404

    def test_adjusting_an_unknown_source_is_a_not_found(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        response = admin_client.patch(_stock_url("ghost", "HB-250"), {"delta": 1}, format="json")
        assert response.status_code == 404

    def test_member_cannot_set_stock(self, member_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        response = member_client.put(_stock_url("main", "HB-250"), {"quantity": 1}, format="json")
        assert response.status_code == 403


class TestPerSourceScope:
    """A per-source manager (guardian grant) may mutate only the source granted."""

    def test_scoped_manager_can_mutate_only_the_granted_source(self) -> None:
        _seed_variant("HB-250", stock=5)
        StockSourceModel.objects.create(code="north", name="North")
        StockSourceModel.objects.create(code="south", name="South")
        # Give both sources a level for HB-250 so the writes touch real rows.
        DjangoStockLevelRepository().set_on_hand("HB-250", StockSourceCode("north"), 0)
        DjangoStockLevelRepository().set_on_hand("HB-250", StockSourceCode("south"), 0)

        user = _user("09120000003")
        build_grant_stock_source_management().execute(user_id=user.pk, source_code="north")
        client = _client(user)

        # May set stock at the granted source ...
        granted = client.put(_stock_url("north", "HB-250"), {"quantity": 10}, format="json")
        assert granted.status_code == 200
        assert granted.data["on_hand"] == 10

        # ... but not at another source (the grant does not leak).
        denied = client.put(_stock_url("south", "HB-250"), {"quantity": 10}, format="json")
        assert denied.status_code == 403

        # Reads are open to any authenticated user.
        assert client.get(_stock_url("south", "HB-250")).status_code == 200


class TestVariantStockPolicy:
    def test_get_returns_the_default_for_an_unset_variant(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)

        response = admin_client.get(_policy_url("HB-250"))

        assert response.status_code == 200
        assert response.data["backorderable"] is False
        assert response.data["low_stock_threshold"] == 0
        assert response.data["backordered"] == 0

    def test_admin_sets_backorder_and_threshold(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)

        response = admin_client.put(
            _policy_url("HB-250"),
            {"backorderable": True, "low_stock_threshold": 3},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["backorderable"] is True
        assert response.data["low_stock_threshold"] == 3
        # Re-reading reflects the stored policy.
        assert admin_client.get(_policy_url("HB-250")).data["backorderable"] is True

    def test_setting_a_policy_for_an_unknown_variant_is_a_not_found(
        self, admin_client: APIClient
    ) -> None:
        response = admin_client.put(
            _policy_url("GHOST-1"),
            {"backorderable": True, "low_stock_threshold": 0},
            format="json",
        )
        assert response.status_code == 404

    def test_a_negative_threshold_is_a_bad_request(self, admin_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        response = admin_client.put(
            _policy_url("HB-250"),
            {"backorderable": False, "low_stock_threshold": -1},
            format="json",
        )
        assert response.status_code == 400

    def test_member_cannot_set_a_policy(self, member_client: APIClient) -> None:
        _seed_variant("HB-250", stock=5)
        response = member_client.put(
            _policy_url("HB-250"),
            {"backorderable": True, "low_stock_threshold": 0},
            format="json",
        )
        assert response.status_code == 403

    def test_reading_a_policy_for_an_unknown_variant_is_a_not_found(
        self, admin_client: APIClient
    ) -> None:
        assert admin_client.get(_policy_url("GHOST-1")).status_code == 404
