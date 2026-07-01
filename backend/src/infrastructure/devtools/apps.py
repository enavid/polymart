"""Django app configuration for developer/E2E tooling.

This app carries no models and ships no runtime behaviour. It exists only to make
management commands (notably ``seed_e2e``) discoverable. It is installed in every
environment, but its commands guard themselves on ``DEBUG`` so they cannot run
against a real deployment.
"""

from __future__ import annotations

from django.apps import AppConfig


class DevtoolsConfig(AppConfig):
    name = "src.infrastructure.devtools"
    label = "devtools"
    verbose_name = "Developer tooling"
    default_auto_field = "django.db.models.BigAutoField"
