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

from src.domain.identity.enums import OtpPurpose
from src.domain.identity.value_objects import PhoneNumber

# E.164 for an Iranian mobile is 13 characters: "+98" + 10 national digits.
_PHONE_MAX_LENGTH = 16
# A hex SHA-256 digest is 64 chars; leave headroom for an algorithm prefix.
_CODE_HASH_MAX_LENGTH = 128


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
        # Global RBAC permission for access administration. The codename mirrors
        # src.domain.identity.permissions.MANAGE_ACCESS; the access registry
        # bundles it into the access_admin role.
        permissions: ClassVar[list[tuple[str, str]]] = [  # type: ignore[assignment]
            ("manage_access", "Can administer access (assign roles and channel scope)"),
        ]

    def __str__(self) -> str:
        return self.phone_number


class OtpChallengeModel(models.Model):
    """Storage representation of a one-time-code challenge.

    Holds only the code's hash, never the code. ``created_at`` is written from the
    application clock (not ``auto_now_add``) so issuance time stays consistent
    with the domain's view of "now".
    """

    _PURPOSE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (purpose.value, purpose.value) for purpose in OtpPurpose
    ]

    phone_number = models.CharField(max_length=_PHONE_MAX_LENGTH)
    purpose = models.CharField(max_length=32, choices=_PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=_CODE_HASH_MAX_LENGTH)
    expires_at = models.DateTimeField()
    max_attempts = models.PositiveSmallIntegerField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        app_label = "identity"
        db_table = "identity_otp_challenge"
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["phone_number", "purpose", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"otp:{self.purpose}:{self.pk}"
