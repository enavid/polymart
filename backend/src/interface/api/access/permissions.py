"""DRF permission classes enforcing two-layer RBAC on channel writes.

Reads are open to any authenticated user; writes require the ``manage_channel``
permission. There are two write surfaces with different scoping rules:

* Creating a channel is a platform-global action (no object exists yet), so it
  requires the permission *globally* -- ``GlobalChannelManagePermission``.
* Mutating an existing channel may be authorised either globally *or* by a
  per-object guardian grant -- ``ScopedChannelManagePermission`` (the detail view
  must call ``check_object_permissions`` with the domain ``Channel``).

Both defer the actual permission decision to the ``AccessControlGateway`` so the
guardian/ORM details stay in infrastructure.
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from src.domain.catalog.permissions import MANAGE_CATALOG
from src.domain.channel.entities import Channel
from src.domain.channel.permissions import MANAGE_CHANNEL
from src.domain.identity.permissions import MANAGE_ACCESS
from src.domain.order.permissions import MANAGE_ORDERS
from src.interface.api.access.container import build_access_gateway


def _is_authenticated(request: Request) -> bool:
    return bool(request.user and request.user.is_authenticated)


class AccessAdminPermission(BasePermission):
    """Gate the access-administration API: requires the global manage_access perm.

    Administering roles/scope is itself a privileged, platform-global action, so
    it is never object-scoped -- a global permission (or superuser) is required.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        if not _is_authenticated(request):
            return False
        return bool(request.user.has_perm(MANAGE_ACCESS.full_name))


class GlobalChannelManagePermission(BasePermission):
    """List/create gate: reads need auth; create needs the global permission."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        # Creating a channel cannot be object-scoped: require the global perm.
        return bool(request.user.has_perm(MANAGE_CHANNEL.full_name))


class CatalogManagePermission(BasePermission):
    """List/create gate for catalog config: reads need auth; writes the global perm.

    Catalog definitions (attributes, product types, products) are platform-global
    configuration, so management is never object-scoped -- a global permission
    (or superuser) is required.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.has_perm(MANAGE_CATALOG.full_name))


class OrderManagePermission(BasePermission):
    """Gate the staff order operations: requires the global manage_orders perm.

    Creating a manual order (a pre-invoice) and reading any order's pre-invoice are
    privileged, platform-global staff actions -- never object-scoped -- so a global
    permission (or superuser) is required. A shopper's own place/read/cancel uses the
    open, owner-scoped storefront endpoints instead and is not gated here.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        if not _is_authenticated(request):
            return False
        return bool(request.user.has_perm(MANAGE_ORDERS.full_name))


class ScopedChannelManagePermission(BasePermission):
    """Detail gate: reads need auth; writes need global *or* per-channel scope.

    ``has_permission`` only verifies authentication so an object-scoped manager
    is not rejected before the object check; the precise decision happens in
    ``has_object_permission`` once the view supplies the target channel.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        return _is_authenticated(request)

    def has_object_permission(self, request: Request, view: Any, obj: Channel) -> bool:
        if request.method in SAFE_METHODS:
            return True
        channel_id = obj.id
        if channel_id is None:  # pragma: no cover - persisted channels always carry an id
            return False
        return build_access_gateway().can_manage_channel(request.user.pk, channel_id)
