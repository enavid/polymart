"""Django app configuration for the address infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class AddressConfig(AppConfig):
    name = "src.infrastructure.address"
    label = "address"
    verbose_name = "Address"
    default_auto_field = "django.db.models.BigAutoField"
