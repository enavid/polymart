"""Django app configuration for the access (RBAC) infrastructure.

The app owns no ORM models; it exists to (a) host the guardian gateway adapter
and (b) keep Django's role layer (Groups) in sync with the domain permission
registry after every migration.
"""

from __future__ import annotations

from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_after_migrate(sender: AppConfig, **_kwargs: Any) -> None:
    """post_migrate receiver: re-project the registry onto Django Groups."""
    # Imported lazily so importing the AppConfig never touches the ORM/registry
    # before the app registry is ready.
    from src.domain.access.registry import build_default_registry
    from src.infrastructure.access.sync import sync_access_control

    sync_access_control(build_default_registry())


class AccessConfig(AppConfig):
    name = "src.infrastructure.access"
    label = "access"
    verbose_name = "Access control"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        post_migrate.connect(
            _sync_after_migrate,
            sender=self,
            dispatch_uid="access.sync_roles",
        )
