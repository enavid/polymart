"""Django app configuration for the catalog infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "src.infrastructure.catalog"
    label = "catalog"
    verbose_name = "Catalog"
    default_auto_field = "django.db.models.BigAutoField"
