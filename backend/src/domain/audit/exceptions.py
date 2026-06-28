"""Domain exceptions for the audit context.

Pure-Python exceptions with no framework coupling. The interface/infrastructure
layers translate them into transport- or framework-level errors.
"""

from __future__ import annotations


class AuditError(Exception):
    """Base class for every audit domain error."""


class InvalidAuditEntryError(AuditError):
    """Raised when an audit entry or field change is built with malformed data."""
