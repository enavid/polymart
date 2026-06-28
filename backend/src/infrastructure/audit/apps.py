"""Django app configuration for the audit infrastructure adapter."""

from __future__ import annotations

from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "src.infrastructure.audit"
    label = "audit"
    verbose_name = "Audit log"
    default_auto_field = "django.db.models.BigAutoField"
