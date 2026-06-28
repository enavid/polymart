"""Access-control permissions owned by the catalog context.

Declaring them next to the domain (rather than in the access context) keeps each
bounded context the owner of its own permissions -- the access registry merely
collects them. ``manage_catalog`` gates every catalog-schema mutation (attributes
now; product types, products, and pricing in later slices).
"""

from __future__ import annotations

from src.domain.access.permissions import PermissionDefinition

CATALOG_RESOURCE = "catalog"

MANAGE_CATALOG = PermissionDefinition(
    codename="manage_catalog",
    label="Can manage the catalog (attributes, product types, products)",
    resource=CATALOG_RESOURCE,
)

# The catalog context's contribution to the platform permission registry.
CATALOG_PERMISSIONS: tuple[PermissionDefinition, ...] = (MANAGE_CATALOG,)
