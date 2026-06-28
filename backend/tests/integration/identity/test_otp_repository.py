"""Integration tests for the Django OTP repository (real database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.domain.identity.entities import OtpChallenge
from src.domain.identity.enums import OtpPurpose
from src.infrastructure.identity.otp_repository import DjangoOtpRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_PHONE = "+989123456789"
_NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=UTC)


def _challenge(**overrides: object) -> OtpChallenge:
    defaults: dict[str, object] = {
        "phone_number": _PHONE,
        "purpose": OtpPurpose.REGISTRATION,
        "code_hash": "deadbeef",
        "expires_at": _NOW + timedelta(minutes=2),
        "max_attempts": 5,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return OtpChallenge(**defaults)  # type: ignore[arg-type]


def test_save_assigns_an_id_and_round_trips_through_the_database() -> None:
    repo = DjangoOtpRepository()

    saved = repo.save(_challenge())

    assert saved.id is not None
    loaded = repo.get_latest(_PHONE, OtpPurpose.REGISTRATION)
    assert loaded is not None
    assert loaded.code_hash == "deadbeef"
    assert loaded.purpose is OtpPurpose.REGISTRATION


def test_get_latest_returns_the_most_recent_challenge() -> None:
    repo = DjangoOtpRepository()
    repo.save(_challenge(code_hash="older", created_at=_NOW))
    repo.save(_challenge(code_hash="newer", created_at=_NOW + timedelta(seconds=90)))

    latest = repo.get_latest(_PHONE, OtpPurpose.REGISTRATION)

    assert latest is not None
    assert latest.code_hash == "newer"


def test_get_latest_is_scoped_by_purpose() -> None:
    repo = DjangoOtpRepository()
    repo.save(_challenge(purpose=OtpPurpose.REGISTRATION))

    assert repo.get_latest(_PHONE, OtpPurpose.PASSWORD_RESET) is None


def test_get_latest_returns_none_when_absent() -> None:
    assert DjangoOtpRepository().get_latest(_PHONE, OtpPurpose.REGISTRATION) is None


def test_save_persists_attempt_and_consumption_updates() -> None:
    repo = DjangoOtpRepository()
    saved = repo.save(_challenge())

    saved.register_failed_attempt()
    saved.consume(_NOW + timedelta(seconds=30))
    repo.save(saved)

    loaded = repo.get_latest(_PHONE, OtpPurpose.REGISTRATION)
    assert loaded is not None
    assert loaded.attempts == 1
    assert loaded.is_consumed is True
