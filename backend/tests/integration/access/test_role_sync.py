"""Integration tests for the registry -> Django Groups projection.

The sync runs automatically on ``post_migrate`` (i.e. during test DB build), so
the role layer should already exist. We also call it directly to prove it is
idempotent.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission

from src.domain.access.registry import CHANNEL_ADMIN_ROLE, build_default_registry
from src.infrastructure.access.sync import sync_access_control

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_channel_admin_group_exists_with_the_manage_permission() -> None:
    group = Group.objects.get(name=CHANNEL_ADMIN_ROLE)

    codenames = {p.codename for p in group.permissions.all()}
    assert "manage_channel" in codenames


def test_the_synced_permission_is_bound_to_the_channel_content_type() -> None:
    group = Group.objects.get(name=CHANNEL_ADMIN_ROLE)
    perm = group.permissions.get(codename="manage_channel")

    # Object scope only works if the permission lives on the channel model.
    assert perm.content_type.app_label == "channel"


def test_sync_is_idempotent() -> None:
    sync_access_control(build_default_registry())
    sync_access_control(build_default_registry())

    group = Group.objects.get(name=CHANNEL_ADMIN_ROLE)
    assert group.permissions.filter(codename="manage_channel").count() == 1
    # A single Permission row backs the codename (no duplicate created).
    assert (
        Permission.objects.filter(
            content_type__app_label="channel", codename="manage_channel"
        ).count()
        == 1
    )
