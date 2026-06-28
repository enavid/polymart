"""Domain exceptions for the identity context.

Pure-Python exceptions with no framework coupling. The interface layer maps them
to transport-level responses; the infrastructure layer may raise them from the
user manager when normalizing input.
"""

from __future__ import annotations


class IdentityError(Exception):
    """Base class for every identity domain error."""


class InvalidPhoneNumberError(IdentityError):
    """Raised when a value is not a valid Iranian mobile number."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid phone number: {value!r}")
        self.value = value
