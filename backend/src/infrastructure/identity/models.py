"""Custom user model and manager (phone-first identity).

The user is a framework concern (Django requires ``AUTH_USER_MODEL`` to be an
``AbstractBaseUser``), so it lives in infrastructure. The one piece of real
business rule -- what a valid phone number is -- is delegated to the domain
``PhoneNumber`` value object, keeping the rule in one pure-Python place.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from src.domain.identity.value_objects import PhoneNumber

# E.164 for an Iranian mobile is 13 characters: "+98" + 10 national digits.
_PHONE_MAX_LENGTH = 16


class UserManager(BaseUserManager["User"]):
    """Creates users, normalizing the phone number through the domain rule."""

    use_in_migrations = True

    def create_user(
        self, phone_number: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        if not phone_number:
            raise ValueError("A phone number is required to create a user.")
        # Raises InvalidPhoneNumberError for malformed input; stores canonical form.
        canonical = PhoneNumber(phone_number).value
        user: User = self.model(phone_number=canonical, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, phone_number: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """A platform user, identified by a canonical Iranian mobile number."""

    phone_number = models.CharField(max_length=_PHONE_MAX_LENGTH, unique=True)
    email = models.EmailField(blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        app_label = "identity"
        db_table = "identity_user"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.phone_number
