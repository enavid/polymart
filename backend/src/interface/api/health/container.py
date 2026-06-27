"""Composition root for the health slice.

Wires concrete infrastructure adapters into the use case. This is the only
place in the slice that knows about both the application and infrastructure
layers.
"""
from __future__ import annotations

from src.application.health.use_cases import GetSystemHealth
from src.infrastructure.health.probes import (
    ApplicationHealthProbe,
    DatabaseHealthProbe,
)


def build_get_system_health() -> GetSystemHealth:
    return GetSystemHealth(
        probes=[ApplicationHealthProbe(), DatabaseHealthProbe()]
    )
