"""Django app configuration for the wallet infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class WalletConfig(AppConfig):
    name = "src.infrastructure.wallet"
    label = "wallet"
    verbose_name = "Wallet"
    default_auto_field = "django.db.models.BigAutoField"
