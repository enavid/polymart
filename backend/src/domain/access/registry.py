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
from src.domain.catalog.permissions import CATALOG_PERMISSIONS, MANAGE_CATALOG
from src.domain.channel.permissions import CHANNEL_PERMISSIONS, MANAGE_CHANNEL
from src.domain.identity.permissions import IDENTITY_PERMISSIONS, MANAGE_ACCESS
from src.domain.order.permissions import MANAGE_ORDERS, ORDER_PERMISSIONS

# Role names are stable identifiers (used as Django Group names); keep them in
# one place so the sync layer and any future assignment UI agree.
CHANNEL_ADMIN_ROLE = "channel_admin"
ACCESS_ADMIN_ROLE = "access_admin"
CATALOG_ADMIN_ROLE = "catalog_admin"
ORDER_ADMIN_ROLE = "order_admin"


def build_default_registry() -> PermissionRegistry:
    """Build the registry with every context's permissions and the base roles."""
    registry = PermissionRegistry()

    for permission in (
        *CHANNEL_PERMISSIONS,
        *IDENTITY_PERMISSIONS,
        *CATALOG_PERMISSIONS,
        *ORDER_PERMISSIONS,
    ):
        registry.register_permission(permission)

    # The global "manage all channels" role. Object-scoped channel managers are
    # granted the same permission per-channel via guardian instead of this role.
    registry.register_role(
        RoleDefinition(
            name=CHANNEL_ADMIN_ROLE,
            permissions=frozenset({MANAGE_CHANNEL.codename}),
        )
    )
    # The access-administration role: assign roles and grant per-channel scope.
    registry.register_role(
        RoleDefinition(
            name=ACCESS_ADMIN_ROLE,
            permissions=frozenset({MANAGE_ACCESS.codename}),
        )
    )
    # The global "manage the catalog" role: define attributes, product types, and
    # products. Catalog config is platform-global, so it is not object-scoped.
    registry.register_role(
        RoleDefinition(
            name=CATALOG_ADMIN_ROLE,
            permissions=frozenset({MANAGE_CATALOG.codename}),
        )
    )
    # The "manage orders" role: create manual orders (pre-invoices) and read any
    # order's pre-invoice. A shopper's own place/read/cancel is not gated by this.
    registry.register_role(
        RoleDefinition(
            name=ORDER_ADMIN_ROLE,
            permissions=frozenset({MANAGE_ORDERS.codename}),
        )
    )

    return registry
