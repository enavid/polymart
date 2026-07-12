"""django-guardian implementation of the AccessControlGateway port.

Bridges the access use cases (and the DRF permission classes) to Django's auth
system: Groups for the role layer, guardian object permissions for the scope
layer. Works in plain ids; the ORM/guardian stay contained here.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm

from src.application.access.ports import AccessControlGateway
from src.domain.access.exceptions import RoleNotFoundError, SubjectNotFoundError
from src.domain.channel.permissions import MANAGE_CHANNEL
from src.domain.inventory.permissions import MANAGE_STOCK_SOURCE
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.inventory.models import StockSourceModel

_User = get_user_model()


class GuardianAccessControl(AccessControlGateway):
    """Role assignment via Groups; channel scope via guardian object permissions.

    Translates ORM "does not exist" failures into access domain exceptions so the
    application/interface layers never see Django's ``DoesNotExist``.
    """

    def assign_role(self, user_id: int, role_name: str) -> None:
        user = self._require_user(user_id)
        try:
            group = Group.objects.get(name=role_name)
        except Group.DoesNotExist:
            raise RoleNotFoundError(role_name) from None
        user.groups.add(group)

    def grant_channel_management(self, user_id: int, channel_id: int) -> None:
        user = self._require_user(user_id)
        channel = ChannelModel.objects.get(pk=channel_id)
        assign_perm(MANAGE_CHANNEL.full_name, user, channel)

    def can_manage_channel(self, user_id: int, channel_id: int) -> bool:
        user = _User.objects.get(pk=user_id)
        # Global/role layer first (also short-circuits superusers); fall back to
        # the per-object grant. has_perm with an object consults guardian.
        if user.has_perm(MANAGE_CHANNEL.full_name):
            return True
        channel = ChannelModel.objects.get(pk=channel_id)
        return user.has_perm(MANAGE_CHANNEL.full_name, channel)

    def grant_stock_source_management(self, user_id: int, source_id: int) -> None:
        user = self._require_user(user_id)
        source = StockSourceModel.objects.get(pk=source_id)
        assign_perm(MANAGE_STOCK_SOURCE.full_name, user, source)

    def can_manage_stock_source(self, user_id: int, source_id: int) -> bool:
        user = _User.objects.get(pk=user_id)
        # Global/role layer first (short-circuits superusers); then the per-source grant.
        if user.has_perm(MANAGE_STOCK_SOURCE.full_name):
            return True
        source = StockSourceModel.objects.get(pk=source_id)
        return user.has_perm(MANAGE_STOCK_SOURCE.full_name, source)

    @staticmethod
    def _require_user(user_id: int) -> Any:
        try:
            return _User.objects.get(pk=user_id)
        except _User.DoesNotExist:
            raise SubjectNotFoundError(user_id) from None
