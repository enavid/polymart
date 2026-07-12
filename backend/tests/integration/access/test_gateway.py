"""Integration tests for the guardian-backed AccessControlGateway adapter.

Exercises both RBAC layers against a real database: role assignment (Groups) and
per-channel object scope (guardian), plus the combined ``can_manage_channel``
check the DRF permission classes rely on.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser

from src.domain.access.registry import CHANNEL_ADMIN_ROLE, INVENTORY_ADMIN_ROLE
from src.infrastructure.access.gateway import GuardianAccessControl
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.inventory.models import StockSourceModel

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def gateway() -> GuardianAccessControl:
    return GuardianAccessControl()


@pytest.fixture
def user() -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number="09120000010", password="pw")


@pytest.fixture
def channel() -> ChannelModel:
    return ChannelModel.objects.create(slug="coffee", name="Coffee", currency_code="IRR")


@pytest.fixture
def source() -> StockSourceModel:
    return StockSourceModel.objects.create(code="north", name="North Warehouse")


class TestRoleLayer:
    def test_assigning_the_channel_admin_role_grants_global_management(
        self, gateway: GuardianAccessControl, user: AbstractBaseUser, channel: ChannelModel
    ) -> None:
        gateway.assign_role(user.pk, CHANNEL_ADMIN_ROLE)

        # Global role => may manage any channel, including ones it was never
        # explicitly scoped to.
        other = ChannelModel.objects.create(slug="tea", name="Tea", currency_code="IRR")
        assert gateway.can_manage_channel(user.pk, channel.pk)
        assert gateway.can_manage_channel(user.pk, other.pk)


class TestObjectScopeLayer:
    def test_grant_scopes_management_to_a_single_channel(
        self, gateway: GuardianAccessControl, user: AbstractBaseUser, channel: ChannelModel
    ) -> None:
        other = ChannelModel.objects.create(slug="tea", name="Tea", currency_code="IRR")

        gateway.grant_channel_management(user.pk, channel.pk)

        assert gateway.can_manage_channel(user.pk, channel.pk) is True
        # The grant does not leak to other channels.
        assert gateway.can_manage_channel(user.pk, other.pk) is False

    def test_user_without_any_grant_cannot_manage(
        self, gateway: GuardianAccessControl, user: AbstractBaseUser, channel: ChannelModel
    ) -> None:
        assert gateway.can_manage_channel(user.pk, channel.pk) is False


class TestStockSourceRoleLayer:
    def test_inventory_admin_role_grants_global_source_management(
        self, gateway: GuardianAccessControl, user: AbstractBaseUser, source: StockSourceModel
    ) -> None:
        gateway.assign_role(user.pk, INVENTORY_ADMIN_ROLE)

        other = StockSourceModel.objects.create(code="south", name="South")
        assert gateway.can_manage_stock_source(user.pk, source.pk)
        assert gateway.can_manage_stock_source(user.pk, other.pk)  # global => any source


class TestStockSourceObjectScopeLayer:
    def test_grant_scopes_management_to_a_single_source(
        self, gateway: GuardianAccessControl, user: AbstractBaseUser, source: StockSourceModel
    ) -> None:
        other = StockSourceModel.objects.create(code="south", name="South")

        gateway.grant_stock_source_management(user.pk, source.pk)

        assert gateway.can_manage_stock_source(user.pk, source.pk) is True
        # The grant does not leak to other sources.
        assert gateway.can_manage_stock_source(user.pk, other.pk) is False

    def test_user_without_any_grant_cannot_manage_a_source(
        self, gateway: GuardianAccessControl, user: AbstractBaseUser, source: StockSourceModel
    ) -> None:
        assert gateway.can_manage_stock_source(user.pk, source.pk) is False
