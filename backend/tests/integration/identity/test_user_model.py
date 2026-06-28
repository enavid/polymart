"""Integration tests for the custom user model and its manager (DB-backed).

Identity is phone-first (Iran). The manager normalizes the phone through the
domain value object so that any spelling maps to one stored canonical form, and
passwords are always hashed -- never stored or comparable in clear text.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from src.domain.identity.exceptions import InvalidPhoneNumberError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCreateUser:
    def test_creates_a_user_with_a_canonical_phone_number(self) -> None:
        user = get_user_model().objects.create_user(
            phone_number="09123456789", password="s3cret-pw"
        )

        assert user.pk is not None
        assert user.phone_number == "+989123456789"
        assert user.is_active is True
        assert user.is_staff is False

    def test_normalizes_phone_so_spellings_are_the_same_identity(self) -> None:
        get_user_model().objects.create_user(
            phone_number="09123456789", password="pw"
        )

        # A different spelling of the same number normalizes to the same canonical
        # value and must collide on the unique key.
        with pytest.raises(IntegrityError):
            get_user_model().objects.create_user(
                phone_number="+989123456789", password="pw"
            )

    def test_rejects_an_invalid_phone_number(self) -> None:
        with pytest.raises(InvalidPhoneNumberError):
            get_user_model().objects.create_user(
                phone_number="not-a-phone", password="pw"
            )

    def test_password_is_hashed_not_stored_in_clear_text(self) -> None:
        user = get_user_model().objects.create_user(
            phone_number="09123456789", password="s3cret-pw"
        )

        assert user.password != "s3cret-pw"
        assert user.check_password("s3cret-pw") is True

    def test_requires_a_phone_number(self) -> None:
        with pytest.raises(ValueError):
            get_user_model().objects.create_user(phone_number="", password="pw")

    def test_username_field_is_the_phone_number(self) -> None:
        user = get_user_model().objects.create_user(
            phone_number="09123456789", password="pw"
        )

        assert user.get_username() == "+989123456789"
        assert get_user_model().USERNAME_FIELD == "phone_number"


class TestCreateSuperuser:
    def test_superuser_has_staff_and_superuser_flags(self) -> None:
        admin = get_user_model().objects.create_superuser(
            phone_number="09123456789", password="pw"
        )

        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_superuser_must_have_staff_flag(self) -> None:
        with pytest.raises(ValueError):
            get_user_model().objects.create_superuser(
                phone_number="09123456789", password="pw", is_staff=False
            )

    def test_superuser_must_have_superuser_flag(self) -> None:
        with pytest.raises(ValueError):
            get_user_model().objects.create_superuser(
                phone_number="09123456789", password="pw", is_superuser=False
            )

    def test_str_is_the_phone_number(self) -> None:
        user = get_user_model().objects.create_user(
            phone_number="09123456789", password="pw"
        )

        assert str(user) == "+989123456789"
