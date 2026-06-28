"""Access-control permissions owned by the identity context.

Administering *who* may do *what* -- assigning roles and per-channel scope -- is a
user-administration capability, so the identity context owns its permission. As
with the channel context, declaring it next to the domain keeps each context the
owner of its permissions; the access registry merely collects them and the sync
layer projects them onto Django Groups.

``manage_access`` gates the access-administration API (role assignment, channel
grants). It is a global permission only: there is no object-scoped notion of
"administer access to this one thing".
"""

from __future__ import annotations

from src.domain.access.permissions import PermissionDefinition

IDENTITY_RESOURCE = "identity"

MANAGE_ACCESS = PermissionDefinition(
    codename="manage_access",
    label="Can administer access (assign roles and channel scope)",
    resource=IDENTITY_RESOURCE,
)

# The identity context's contribution to the platform permission registry.
IDENTITY_PERMISSIONS: tuple[PermissionDefinition, ...] = (MANAGE_ACCESS,)
