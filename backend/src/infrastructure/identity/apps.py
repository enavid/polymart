"""Django app configuration for the identity infrastructure adapter."""
from __future__ import annotations

from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = "src.infrastructure.identity"
    label = "identity"
    verbose_name = "Identity"
    default_auto_field = "django.db.models.BigAutoField"
