"""Access-control permissions owned by the order context.

Declaring them next to the domain (rather than in the access context) keeps each
bounded context the owner of its own permissions -- the access registry merely
collects them. ``manage_orders`` gates the staff-facing order operations that are not
a shopper's own self-service: creating a manual order (a pre-invoice) and reading any
order's pre-invoice. A shopper's own place/read/cancel remains open (owner-scoped),
not gated by this permission.
"""

from __future__ import annotations

from src.domain.access.permissions import PermissionDefinition

ORDER_RESOURCE = "order"

MANAGE_ORDERS = PermissionDefinition(
    codename="manage_orders",
    label="Can manage orders (create manual orders and issue pre-invoices)",
    resource=ORDER_RESOURCE,
)

# The order context's contribution to the platform permission registry.
ORDER_PERMISSIONS: tuple[PermissionDefinition, ...] = (MANAGE_ORDERS,)
