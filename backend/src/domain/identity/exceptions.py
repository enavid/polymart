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


class OtpError(IdentityError):
    """Base class for one-time-code verification failures."""


class InvalidOtpError(OtpError):
    """Raised when no matching, still-valid code exists for the submitted input.

    Deliberately covers "wrong code", "no code issued", and "already used" with a
    single error so the response cannot distinguish them.
    """


class OtpExpiredError(OtpError):
    """Raised when the code exists but its validity window has passed."""


class OtpMaxAttemptsError(OtpError):
    """Raised when the code's wrong-guess budget is exhausted (locked out)."""


class UserAlreadyExistsError(IdentityError):
    """Raised when registering a phone number that already has an account."""

    def __init__(self, phone_number: str) -> None:
        super().__init__("a user with this phone number already exists")
        self.phone_number = phone_number


class UserNotFoundError(IdentityError):
    """Raised when an operation targets a phone number with no account."""

    def __init__(self, phone_number: str) -> None:
        super().__init__("no user exists for this phone number")
        self.phone_number = phone_number
