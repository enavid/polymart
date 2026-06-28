"""Entities for the identity domain.

``OtpChallenge`` is the security-critical heart of the OTP flows: it captures a
one-time code's lifecycle (expiry, bounded wrong guesses, single use) as pure
business rules. It holds only the *hash* of the code -- never the code itself --
so a leaked persistence row cannot reveal a live secret. This is plain Python:
no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.identity.enums import OtpPurpose

_MIN_ATTEMPT_LIMIT = 1


@dataclass
class OtpChallenge:
    """A pending one-time code, identified in storage by ``id`` once persisted."""

    phone_number: str
    purpose: OtpPurpose
    code_hash: str
    expires_at: datetime
    max_attempts: int
    created_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < _MIN_ATTEMPT_LIMIT:
            raise ValueError("max_attempts must be at least 1")
        if not self.code_hash:
            raise ValueError("code_hash must not be empty")

    @property
    def is_consumed(self) -> bool:
        """Whether the code has already been spent."""
        return self.consumed_at is not None

    @property
    def attempts_exhausted(self) -> bool:
        """Whether the wrong-guess budget is used up (brute-force guard)."""
        return self.attempts >= self.max_attempts

    def is_expired(self, now: datetime) -> bool:
        """Whether the code is no longer valid at ``now`` (deadline inclusive)."""
        return now >= self.expires_at

    def register_failed_attempt(self) -> None:
        """Record one incorrect guess against the attempt budget."""
        self.attempts += 1

    def consume(self, now: datetime) -> None:
        """Mark the code as spent so it can never be replayed."""
        self.consumed_at = now
