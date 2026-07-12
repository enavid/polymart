"""Composition root for the access slice.

Wires the concrete guardian adapter (and the audit recorder) into the application
ports. The DRF permission classes and assignment views depend on these factories,
never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.access.ports import AccessControlGateway
from src.application.access.use_cases import (
    AssignRole,
    GrantChannelManagement,
    GrantStockSourceManagement,
)
from src.application.identity.admin_use_cases import AdminCreateUser, ListUserAccounts
from src.infrastructure.access.gateway import GuardianAccessControl
from src.infrastructure.channel.repositories import DjangoChannelRepository
from src.infrastructure.identity.user_directory import DjangoUserDirectory
from src.infrastructure.inventory.repositories import DjangoStockSourceRepository
from src.interface.api.audit.container import build_audit_recorder


def build_access_gateway() -> AccessControlGateway:
    return GuardianAccessControl()


def build_list_user_accounts() -> ListUserAccounts:
    return ListUserAccounts(DjangoUserDirectory())


def build_admin_create_user() -> AdminCreateUser:
    return AdminCreateUser(DjangoUserDirectory(), build_audit_recorder())


def build_assign_role() -> AssignRole:
    return AssignRole(build_access_gateway(), build_audit_recorder())


def build_grant_channel_management() -> GrantChannelManagement:
    return GrantChannelManagement(
        build_access_gateway(), DjangoChannelRepository(), build_audit_recorder()
    )


def build_grant_stock_source_management() -> GrantStockSourceManagement:
    return GrantStockSourceManagement(
        build_access_gateway(), DjangoStockSourceRepository(), build_audit_recorder()
    )
