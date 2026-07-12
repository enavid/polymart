"""Ports (interfaces) for the access (RBAC) use cases.

The application layer depends only on this abstraction; the concrete adapter
(django-guardian + Django Groups) lives in infrastructure and is injected at the
composition root, keeping the dependency rule pointing inward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AccessControlGateway(ABC):
    """Boundary for granting and checking role/object permissions.

    Works in plain identifiers (user id, channel id), never ORM instances, so the
    application layer stays free of framework types.
    """

    @abstractmethod
    def assign_role(self, user_id: int, role_name: str) -> None:
        """Add the user to the role (global/role layer)."""

    @abstractmethod
    def grant_channel_management(self, user_id: int, channel_id: int) -> None:
        """Grant the user object-scoped management of one channel."""

    @abstractmethod
    def can_manage_channel(self, user_id: int, channel_id: int) -> bool:
        """Return whether the user may manage this channel, by either layer
        (a global role/permission or a per-object grant)."""

    @abstractmethod
    def grant_stock_source_management(self, user_id: int, source_id: int) -> None:
        """Grant the user object-scoped management of one stock source (warehouse)."""

    @abstractmethod
    def can_manage_stock_source(self, user_id: int, source_id: int) -> bool:
        """Return whether the user may manage this stock source, by either layer
        (a global role/permission or a per-object grant)."""
