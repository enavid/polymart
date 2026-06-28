"""Django app configuration for the channel infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class ChannelConfig(AppConfig):
    name = "src.infrastructure.channel"
    label = "channel"
    verbose_name = "Channel"
    default_auto_field = "django.db.models.BigAutoField"
