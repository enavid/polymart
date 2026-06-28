"""Concrete health probes (adapters)."""

from __future__ import annotations

from django.db import connection

from src.application.health.ports import HealthProbe
from src.domain.health.entities import ComponentHealth, HealthState


class DatabaseHealthProbe(HealthProbe):
    """Verify database connectivity with a trivial query."""

    @property
    def name(self) -> str:
        return "database"

    def check(self) -> ComponentHealth:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return ComponentHealth(name=self.name, state=HealthState.HEALTHY)


class ApplicationHealthProbe(HealthProbe):
    """Report that the application process itself is responsive."""

    @property
    def name(self) -> str:
        return "application"

    def check(self) -> ComponentHealth:
        return ComponentHealth(name=self.name, state=HealthState.HEALTHY)
