"""Health domain entities.

This is the walking-skeleton domain slice: it demonstrates the dependency rule
(pure Python, zero framework imports) and is exercised end to end by the test
suite, Docker, and CI.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ComponentHealth:
    """Health of a single subsystem (database, cache, ...)."""

    name: str
    state: HealthState
    detail: str = ""


@dataclass(frozen=True)
class HealthReport:
    """Aggregated health across all probed components."""

    components: tuple[ComponentHealth, ...]

    @property
    def state(self) -> HealthState:
        states = {component.state for component in self.components}
        if HealthState.UNHEALTHY in states:
            return HealthState.UNHEALTHY
        if HealthState.DEGRADED in states:
            return HealthState.DEGRADED
        return HealthState.HEALTHY
