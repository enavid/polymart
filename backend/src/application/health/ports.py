"""Ports (interfaces) for the health use cases."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.health.entities import ComponentHealth


class HealthProbe(ABC):
    """A pluggable check for a single subsystem.

    Concrete adapters (database, cache, message broker, ...) live in the
    infrastructure layer and are injected into the use case.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def check(self) -> ComponentHealth: ...
