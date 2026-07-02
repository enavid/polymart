"""Django app configuration for the order infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class OrderConfig(AppConfig):
    name = "src.infrastructure.order"
    label = "order"
    verbose_name = "Order"
    default_auto_field = "django.db.models.BigAutoField"
