"""URL patterns for the health slice."""
from __future__ import annotations

from django.urls import path

from src.interface.api.health.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
]
