"""Unit tests for the OTP domain entities.

The ``OtpChallenge`` entity owns the security-critical lifecycle rules of a
one-time code: it expires, it tolerates only a bounded number of wrong guesses,
and it can be spent exactly once. These rules are pure Python and must hold
independently of any storage or transport.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose

_NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)
_TTL = timedelta(minutes=2)


def _challenge(**overrides: object) -> OtpChallenge:
    defaults: dict[str, object] = {
        "phone_number": "+989123456789",
        "purpose": OtpPurpose.REGISTRATION,
        "code_hash": "hashed",
        "expires_at": _NOW + _TTL,
        "max_attempts": 5,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return OtpChallenge(**defaults)  # type: ignore[arg-type]


class TestOtpChallengeExpiry:
    def test_is_not_expired_before_the_deadline(self) -> None:
        assert _challenge().is_expired(_NOW + _TTL - timedelta(microseconds=1)) is False

    def test_is_expired_exactly_at_the_deadline(self) -> None:
        # The deadline itself counts as expired: no validity window leaks past it.
        assert _challenge().is_expired(_NOW + _TTL) is True

    def test_is_expired_after_the_deadline(self) -> None:
        assert _challenge().is_expired(_NOW + _TTL + timedelta(seconds=1)) is True


class TestOtpChallengeAttempts:
    def test_starts_with_no_attempts(self) -> None:
        assert _challenge().attempts == 0
        assert _challenge().attempts_exhausted is False

    def test_registers_failed_attempts(self) -> None:
        challenge = _challenge(max_attempts=3)

        challenge.register_failed_attempt()
        challenge.register_failed_attempt()

        assert challenge.attempts == 2
        assert challenge.attempts_exhausted is False

    def test_is_exhausted_once_the_limit_is_reached(self) -> None:
        challenge = _challenge(max_attempts=2)

        challenge.register_failed_attempt()
        challenge.register_failed_attempt()

        assert challenge.attempts_exhausted is True


class TestOtpChallengeConsumption:
    def test_starts_unconsumed(self) -> None:
        assert _challenge().is_consumed is False

    def test_can_be_consumed_once(self) -> None:
        challenge = _challenge()

        challenge.consume(_NOW)

        assert challenge.is_consumed is True
        assert challenge.consumed_at == _NOW


class TestOtpChallengeValidation:
    def test_rejects_a_non_positive_attempt_limit(self) -> None:
        with pytest.raises(ValueError, match="max_attempts"):
            _challenge(max_attempts=0)

    def test_rejects_an_empty_code_hash(self) -> None:
        with pytest.raises(ValueError, match="code_hash"):
            _challenge(code_hash="")
