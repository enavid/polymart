"""URL patterns for the audit read slice."""

from __future__ import annotations

from django.urls import path

from src.interface.api.audit.views import AuditLogView

urlpatterns = [
    path("audit/entries/", AuditLogView.as_view(), name="audit-entry-list"),
]
