"""Django app configuration for the payment infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class PaymentConfig(AppConfig):
    name = "src.infrastructure.payment"
    label = "payment"
    verbose_name = "Payment"
    default_auto_field = "django.db.models.BigAutoField"
