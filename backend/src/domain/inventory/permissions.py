"""Access-control permissions owned by the inventory context.

Each bounded context owns its permissions; the access registry merely collects them.
``manage_stock_source`` is a single permission usable at both RBAC layers:

* granted globally (via a role/Group) -> manage every stock source, including
  creating new ones;
* granted per-object (via django-guardian) -> manage only that one source's stock.

``resource`` is the ``inventory`` app-label, so the sync layer finds the Django
``Permission`` row on the ``StockSourceModel`` content type (which declares the same
codename in its ``Meta.permissions``) -- the object type a per-source grant binds to.
"""

from __future__ import annotations

from src.domain.access.permissions import PermissionDefinition

STOCK_SOURCE_RESOURCE = "inventory"

MANAGE_STOCK_SOURCE = PermissionDefinition(
    codename="manage_stock_source",
    label="Can manage stock sources (create, set/adjust per-source stock)",
    resource=STOCK_SOURCE_RESOURCE,
)

# The inventory context's contribution to the platform permission registry.
INVENTORY_PERMISSIONS: tuple[PermissionDefinition, ...] = (MANAGE_STOCK_SOURCE,)
