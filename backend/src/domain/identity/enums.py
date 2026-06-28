"""Enumerations for the identity domain.

Pure Python, no framework coupling. ``OtpPurpose`` scopes a one-time code to a
single flow so a code minted for registration can never be replayed against
password reset (or vice versa).
"""

from __future__ import annotations

from enum import Enum


class OtpPurpose(Enum):
    """The flow a one-time code belongs to."""

    REGISTRATION = "registration"
    PASSWORD_RESET = "password_reset"  # nosec B105 - a flow name, not a credential
