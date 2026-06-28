"""Unit tests for the access permission registry (pure domain, no framework).

The registry is the extension point the roadmap calls for: bounded contexts (and
future plugins) declare their permissions and role bundles here, and the
infrastructure layer later projects them onto Django Groups/Permissions. These
tests pin the registry's invariants without touching Django.
"""

from __future__ import annotations

import pytest

from src.domain.access.exceptions import (
    DuplicatePermissionError,
    DuplicateRoleError,
    InvalidPermissionDefinitionError,
    UnknownPermissionError,
)
from src.domain.access.permissions import (
    PermissionDefinition,
    PermissionRegistry,
    RoleDefinition,
)


def _perm(codename: str = "manage_channel", resource: str = "channel") -> PermissionDefinition:
    return PermissionDefinition(codename=codename, label="Can manage", resource=resource)


class TestPermissionDefinition:
    def test_full_name_is_app_label_dot_codename(self) -> None:
        # The full name is the exact string Django's ``has_perm`` expects.
        assert _perm().full_name == "channel.manage_channel"

    @pytest.mark.parametrize("codename", ["", "Manage", "manage channel", "manage-channel", "1bad"])
    def test_rejects_a_malformed_codename(self, codename: str) -> None:
        with pytest.raises(InvalidPermissionDefinitionError):
            _perm(codename=codename)

    @pytest.mark.parametrize("resource", ["", "Channel", "ch annel", "ch-annel"])
    def test_rejects_a_malformed_resource(self, resource: str) -> None:
        with pytest.raises(InvalidPermissionDefinitionError):
            _perm(resource=resource)

    def test_rejects_a_blank_label(self) -> None:
        with pytest.raises(InvalidPermissionDefinitionError):
            PermissionDefinition(codename="manage_channel", label="  ", resource="channel")

    def test_is_immutable(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
            _perm().codename = "other"  # type: ignore[misc]


class TestRoleDefinition:
    def test_rejects_a_blank_name(self) -> None:
        with pytest.raises(InvalidPermissionDefinitionError):
            RoleDefinition(name="  ", permissions=frozenset())


class TestPermissionRegistry:
    def test_registers_and_lists_permissions_sorted_by_codename(self) -> None:
        registry = PermissionRegistry()
        registry.register_permission(_perm(codename="view_channel"))
        registry.register_permission(_perm(codename="manage_channel"))

        assert [p.codename for p in registry.permissions] == ["manage_channel", "view_channel"]

    def test_rejects_a_duplicate_permission_codename(self) -> None:
        registry = PermissionRegistry()
        registry.register_permission(_perm())

        with pytest.raises(DuplicatePermissionError):
            registry.register_permission(_perm())

    def test_registers_a_role_referencing_known_permissions(self) -> None:
        registry = PermissionRegistry()
        registry.register_permission(_perm())
        registry.register_role(
            RoleDefinition(name="channel_admin", permissions=frozenset({"manage_channel"}))
        )

        assert [r.name for r in registry.roles] == ["channel_admin"]

    def test_rejects_a_role_referencing_an_unknown_permission(self) -> None:
        registry = PermissionRegistry()

        with pytest.raises(UnknownPermissionError):
            registry.register_role(
                RoleDefinition(name="ghost", permissions=frozenset({"does_not_exist"}))
            )

    def test_rejects_a_duplicate_role_name(self) -> None:
        registry = PermissionRegistry()
        registry.register_permission(_perm())
        role = RoleDefinition(name="channel_admin", permissions=frozenset({"manage_channel"}))
        registry.register_role(role)

        with pytest.raises(DuplicateRoleError):
            registry.register_role(role)

    def test_permission_lookup_by_codename(self) -> None:
        registry = PermissionRegistry()
        defn = _perm()
        registry.register_permission(defn)

        assert registry.permission("manage_channel") is defn

    def test_lookup_of_an_unknown_codename_raises(self) -> None:
        with pytest.raises(UnknownPermissionError):
            PermissionRegistry().permission("nope")


class TestDefaultRegistry:
    def test_includes_the_channel_management_permission_and_role(self) -> None:
        from src.domain.access.registry import build_default_registry

        registry = build_default_registry()

        assert registry.permission("manage_channel").resource == "channel"
        role_names = {r.name for r in registry.roles}
        assert "channel_admin" in role_names
        admin = next(r for r in registry.roles if r.name == "channel_admin")
        assert "manage_channel" in admin.permissions

    def test_includes_the_access_management_permission_and_role(self) -> None:
        from src.domain.access.registry import build_default_registry

        registry = build_default_registry()

        # manage_access is hosted on the identity app's content type.
        assert registry.permission("manage_access").resource == "identity"
        admin = next(r for r in registry.roles if r.name == "access_admin")
        assert "manage_access" in admin.permissions
