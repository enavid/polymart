"""Health use cases (interactors)."""
from __future__ import annotations

from collections.abc import Sequence

import structlog

from src.application.health.ports import HealthProbe
from src.domain.health.entities import ComponentHealth, HealthReport, HealthState

logger = structlog.get_logger(__name__)

# Detail returned to clients when a probe fails. The health endpoint is public
# (AllowAny), so the real exception text -- which can carry connection strings,
# hostnames, or driver internals -- is logged server-side and never exposed.
PROBE_FAILURE_DETAIL = "unavailable"


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
                logger.error(
                    "health_probe_failed",
                    probe=probe.name,
                    error=str(exc),
                    exc_info=True,
                )
                components.append(
                    ComponentHealth(
                        name=probe.name,
                        state=HealthState.UNHEALTHY,
                        detail=PROBE_FAILURE_DETAIL,
                    )
                )
        return HealthReport(components=tuple(components))
