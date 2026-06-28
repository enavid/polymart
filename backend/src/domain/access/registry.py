"""Assembly of the platform's default permission registry.

Each bounded context contributes its permission definitions; roles bundle them
into named sets. Adding a new context is a matter of registering its permissions
here (or, later, via a plugin entry point) -- no change to the enforcement code.
"""

from __future__ import annotations

from src.domain.access.permissions import (
    PermissionRegistry,
    RoleDefinition,
)
from src.domain.channel.permissions import CHANNEL_PERMISSIONS, MANAGE_CHANNEL

# Role names are stable identifiers (used as Django Group names); keep them in
# one place so the sync layer and any future assignment UI agree.
CHANNEL_ADMIN_ROLE = "channel_admin"


def build_default_registry() -> PermissionRegistry:
    """Build the registry with every context's permissions and the base roles."""
    registry = PermissionRegistry()

    for permission in CHANNEL_PERMISSIONS:
        registry.register_permission(permission)

    # The global "manage all channels" role. Object-scoped channel managers are
    # granted the same permission per-channel via guardian instead of this role.
    registry.register_role(
        RoleDefinition(
            name=CHANNEL_ADMIN_ROLE,
            permissions=frozenset({MANAGE_CHANNEL.codename}),
        )
    )

    return registry
