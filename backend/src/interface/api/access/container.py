"""Composition root for the access slice.

Wires the concrete guardian adapter into the application port. The DRF permission
classes and (future) assignment views depend on these factories, never on the
infrastructure layer directly.
"""

from __future__ import annotations

from src.application.access.ports import AccessControlGateway
from src.infrastructure.access.gateway import GuardianAccessControl


def build_access_gateway() -> AccessControlGateway:
    return GuardianAccessControl()
