"""Domain exceptions for the access (RBAC) context.

Pure-Python exceptions with no framework coupling. The interface/infrastructure
layers translate them into transport- or framework-level errors.
"""

from __future__ import annotations


class AccessError(Exception):
    """Base class for every access/RBAC domain error."""


class InvalidPermissionDefinitionError(AccessError):
    """Raised when a permission or role is declared with malformed fields."""


class DuplicatePermissionError(AccessError):
    """Raised when two permissions are registered under the same codename."""

    def __init__(self, codename: str) -> None:
        super().__init__(f"permission already registered: {codename!r}")
        self.codename = codename


class DuplicateRoleError(AccessError):
    """Raised when two roles are registered under the same name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"role already registered: {name!r}")
        self.name = name


class UnknownPermissionError(AccessError):
    """Raised when a codename is referenced that no permission defines."""

    def __init__(self, codename: str) -> None:
        super().__init__(f"unknown permission: {codename!r}")
        self.codename = codename
