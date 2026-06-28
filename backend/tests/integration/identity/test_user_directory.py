"""Integration tests for the Django user directory adapter (real database).

Pin the translation of ORM-specific failures into domain exceptions so the
application layer never sees a framework leak.
"""

from __future__ import annotations

import pytest

from src.domain.identity.enums import OtpPurpose
from src.domain.identity.exceptions import UserAlreadyExistsError, UserNotFoundError
from src.infrastructure.identity.models import OtpChallengeModel
from src.infrastructure.identity.user_directory import DjangoUserDirectory

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CANONICAL = "+989123456789"


def test_create_returns_an_id_and_reports_existence() -> None:
    directory = DjangoUserDirectory()

    user_id = directory.create(_CANONICAL, password="pw-long-enough", full_name="Ada", email="")

    assert isinstance(user_id, int)
    assert directory.exists(_CANONICAL) is True


def test_create_rejects_a_duplicate_phone() -> None:
    directory = DjangoUserDirectory()
    directory.create(_CANONICAL, password="pw-long-enough", full_name="", email="")

    with pytest.raises(UserAlreadyExistsError):
        directory.create(_CANONICAL, password="other-password", full_name="", email="")


def test_set_password_returns_the_user_id() -> None:
    directory = DjangoUserDirectory()
    created = directory.create(_CANONICAL, password="pw-long-enough", full_name="", email="")

    updated = directory.set_password(_CANONICAL, "a-new-password")

    assert updated == created


def test_set_password_rejects_an_unknown_phone() -> None:
    with pytest.raises(UserNotFoundError):
        DjangoUserDirectory().set_password(_CANONICAL, "a-new-password")


def test_otp_challenge_model_has_a_readable_repr() -> None:
    model = OtpChallengeModel.objects.create(
        phone_number=_CANONICAL,
        purpose=OtpPurpose.REGISTRATION.value,
        code_hash="deadbeef",
        expires_at="2026-06-28T12:00:00Z",
        max_attempts=5,
        created_at="2026-06-28T11:58:00Z",
    )

    assert str(model) == f"otp:{OtpPurpose.REGISTRATION.value}:{model.pk}"
