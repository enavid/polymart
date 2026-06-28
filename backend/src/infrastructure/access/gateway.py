"""django-guardian implementation of the AccessControlGateway port.

Bridges the access use cases (and the DRF permission classes) to Django's auth
system: Groups for the role layer, guardian object permissions for the scope
layer. Works in plain ids; the ORM/guardian stay contained here.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm

from src.application.access.ports import AccessControlGateway
from src.domain.channel.permissions import MANAGE_CHANNEL
from src.infrastructure.channel.models import ChannelModel

_User = get_user_model()


class GuardianAccessControl(AccessControlGateway):
    """Role assignment via Groups; channel scope via guardian object permissions."""

    def assign_role(self, user_id: int, role_name: str) -> None:
        user = _User.objects.get(pk=user_id)
        group = Group.objects.get(name=role_name)
        user.groups.add(group)

    def grant_channel_management(self, user_id: int, channel_id: int) -> None:
        user = _User.objects.get(pk=user_id)
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
