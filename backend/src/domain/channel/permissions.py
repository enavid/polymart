"""Access-control permissions owned by the channel context.

Declaring them next to the domain (rather than in the access context) keeps each
bounded context the owner of its own permissions -- the access registry merely
collects them. ``manage_channel`` is intentionally a single permission usable at
both RBAC layers:

* granted globally (via a role/Group) -> manage every channel, including
  creating new ones;
* granted per-object (via django-guardian) -> manage only that one channel.
"""

from __future__ import annotations

from src.domain.access.permissions import PermissionDefinition

CHANNEL_RESOURCE = "channel"

MANAGE_CHANNEL = PermissionDefinition(
    codename="manage_channel",
    label="Can manage channels (create, activate, deactivate)",
    resource=CHANNEL_RESOURCE,
)

# The channel context's contribution to the platform permission registry.
CHANNEL_PERMISSIONS: tuple[PermissionDefinition, ...] = (MANAGE_CHANNEL,)
