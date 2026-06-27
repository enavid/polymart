"""Health use cases (interactors)."""
from __future__ import annotations

from collections.abc import Sequence

from src.application.health.ports import HealthProbe
from src.domain.health.entities import ComponentHealth, HealthReport, HealthState


class GetSystemHealth:
    """Aggregate the health of all injected probes into a single report.

    A probe that raises is treated as an unhealthy component rather than
    failing the whole report, so the endpoint always returns a useful answer.
    """

    def __init__(self, probes: Sequence[HealthProbe]) -> None:
        self._probes = probes

    def execute(self) -> HealthReport:
        components: list[ComponentHealth] = []
        for probe in self._probes:
            try:
                components.append(probe.check())
            except Exception as exc:  # any failure means the component is unhealthy
                components.append(
                    ComponentHealth(
                        name=probe.name,
                        state=HealthState.UNHEALTHY,
                        detail=str(exc),
                    )
                )
        return HealthReport(components=tuple(components))
