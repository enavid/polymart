"""Unit tests for the GetSystemHealth use case.

These run against fake probes with no database or framework, demonstrating the
payoff of clean architecture: business logic is testable in isolation.
"""
from __future__ import annotations

from src.application.health.ports import HealthProbe
from src.application.health.use_cases import GetSystemHealth
from src.domain.health.entities import ComponentHealth, HealthState


class _FakeProbe(HealthProbe):
    def __init__(self, name: str, state: HealthState) -> None:
        self._name = name
        self._state = state

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> ComponentHealth:
        return ComponentHealth(name=self._name, state=self._state)


class _ExplodingProbe(HealthProbe):
    @property
    def name(self) -> str:
        return "exploding"

    def check(self) -> ComponentHealth:
        raise RuntimeError("connection refused")


def test_all_probes_healthy_yields_healthy_report() -> None:
    use_case = GetSystemHealth(
        probes=[
            _FakeProbe("application", HealthState.HEALTHY),
            _FakeProbe("database", HealthState.HEALTHY),
        ]
    )

    report = use_case.execute()

    assert report.state is HealthState.HEALTHY
    assert len(report.components) == 2


def test_a_degraded_probe_degrades_the_report() -> None:
    use_case = GetSystemHealth(
        probes=[
            _FakeProbe("application", HealthState.HEALTHY),
            _FakeProbe("cache", HealthState.DEGRADED),
        ]
    )

    report = use_case.execute()

    assert report.state is HealthState.DEGRADED


def test_an_unhealthy_probe_makes_the_report_unhealthy() -> None:
    use_case = GetSystemHealth(
        probes=[
            _FakeProbe("application", HealthState.HEALTHY),
            _FakeProbe("database", HealthState.UNHEALTHY),
        ]
    )

    report = use_case.execute()

    assert report.state is HealthState.UNHEALTHY


def test_a_raising_probe_is_reported_as_unhealthy() -> None:
    use_case = GetSystemHealth(probes=[_ExplodingProbe()])

    report = use_case.execute()

    assert report.state is HealthState.UNHEALTHY
    assert report.components[0].detail == "connection refused"
