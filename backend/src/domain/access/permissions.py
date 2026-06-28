"""The permission registry: the platform's catalogue of RBAC permissions/roles.

This is pure domain. A ``PermissionDefinition`` describes a single permission, a
``RoleDefinition`` bundles permissions under a name, and ``PermissionRegistry``
collects both with uniqueness/referential guarantees.

The registry is deliberately framework-free so it can be the shared extension
point the roadmap asks for: each bounded context (and, later, third-party
plugins) declares its permissions here, and the infrastructure layer projects
them onto Django Groups/Permissions. The two-layer RBAC model is:

* role layer  -> a ``RoleDefinition`` becomes a Django ``Group`` (global scope);
* object layer -> the same codenames are granted per-object via django-guardian.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.domain.access.exceptions import (
    DuplicatePermissionError,
    DuplicateRoleError,
    InvalidPermissionDefinitionError,
    UnknownPermissionError,
)

# Django codenames / app-labels: a lowercase identifier (letter first), the same
# shape ``has_perm("<app_label>.<codename>")`` relies on.
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class PermissionDefinition:
    """One permission. ``resource`` maps to a Django app-label at sync time."""

    codename: str
    label: str
    resource: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER_RE.match(self.codename):
            raise InvalidPermissionDefinitionError(f"invalid codename: {self.codename!r}")
        if not _IDENTIFIER_RE.match(self.resource):
            raise InvalidPermissionDefinitionError(f"invalid resource: {self.resource!r}")
        if not self.label.strip():
            raise InvalidPermissionDefinitionError("permission label must not be blank")

    @property
    def full_name(self) -> str:
        """The ``app_label.codename`` string Django's ``has_perm`` expects."""
        return f"{self.resource}.{self.codename}"


@dataclass(frozen=True)
class RoleDefinition:
    """A named bundle of permission codenames (projected to a Django Group)."""

    name: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidPermissionDefinitionError("role name must not be blank")


class PermissionRegistry:
    """Collects permission and role definitions with integrity guarantees."""

    def __init__(self) -> None:
        self._permissions: dict[str, PermissionDefinition] = {}
        self._roles: dict[str, RoleDefinition] = {}

    def register_permission(self, definition: PermissionDefinition) -> None:
        if definition.codename in self._permissions:
            raise DuplicatePermissionError(definition.codename)
        self._permissions[definition.codename] = definition

    def register_role(self, definition: RoleDefinition) -> None:
        if definition.name in self._roles:
            raise DuplicateRoleError(definition.name)
        # A role may only reference permissions that already exist, so the
        # projection onto Django Groups can never dangle.
        for codename in definition.permissions:
            if codename not in self._permissions:
                raise UnknownPermissionError(codename)
        self._roles[definition.name] = definition

    def permission(self, codename: str) -> PermissionDefinition:
        try:
            return self._permissions[codename]
        except KeyError:
            raise UnknownPermissionError(codename) from None

    @property
    def permissions(self) -> tuple[PermissionDefinition, ...]:
        return tuple(self._permissions[c] for c in sorted(self._permissions))

    @property
    def roles(self) -> tuple[RoleDefinition, ...]:
        return tuple(self._roles[n] for n in sorted(self._roles))
