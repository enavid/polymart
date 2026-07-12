"""Django app configuration for the inventory infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = "src.infrastructure.inventory"
    label = "inventory"
    verbose_name = "Inventory"
    default_auto_field = "django.db.models.BigAutoField"
