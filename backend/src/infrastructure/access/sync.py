"""Project the domain permission registry onto Django's auth tables.

Django Groups are the role layer of the two-layer RBAC model. This module turns
each ``RoleDefinition`` into a Group carrying the corresponding ``Permission``
rows. It is idempotent: it ensures content types and permissions exist (so it
does not depend on app-migration ordering) and then re-syncs each group's
permission set, so running it repeatedly converges on the declared state.

It is wired to ``post_migrate`` (see ``apps.AccessConfig``) so the role layer is
always in step with the registry after any migration, including the test DB
build.
"""

from __future__ import annotations

import structlog
from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.management import create_contenttypes

from src.domain.access.permissions import PermissionRegistry

logger = structlog.get_logger(__name__)


def _ensure_permissions_exist() -> None:
    """Force content types and permissions for every app to exist now.

    ``post_migrate`` receivers fire per app in an arbitrary order, so a custom
    permission this sync needs may not have been created yet by its own app's
    handler. Creating them here (idempotently) removes that ordering hazard.
    """
    for config in apps.get_app_configs():
        create_contenttypes(config, verbosity=0)
    for config in apps.get_app_configs():
        create_permissions(config, verbosity=0)


def sync_access_control(registry: PermissionRegistry) -> None:
    """Create/refresh a Django Group for every role in the registry."""
    _ensure_permissions_exist()

    for role in registry.roles:
        group, _created = Group.objects.get_or_create(name=role.name)
        permissions = [
            Permission.objects.get(
                content_type__app_label=registry.permission(codename).resource,
                codename=codename,
            )
            for codename in sorted(role.permissions)
        ]
        group.permissions.set(permissions)
        logger.info(
            "access_role_synced",
            role=role.name,
            permission_count=len(permissions),
        )
