"""Django ORM implementation of the UserDirectory port.

Bridges the OTP use cases to the custom user model, translating ORM-specific
failures into domain exceptions so the application layer never sees a framework
leak. Returns plain ids, never ORM instances.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from src.application.identity.ports import UserDirectory
from src.domain.identity.exceptions import UserAlreadyExistsError, UserNotFoundError
from src.infrastructure.identity.models import User


class DjangoUserDirectory(UserDirectory):
    """Account lookups and mutations backed by the ``User`` model."""

    def exists(self, phone_number: str) -> bool:
        return User.objects.filter(phone_number=phone_number).exists()

    def create(self, phone_number: str, *, password: str, full_name: str, email: str) -> int:
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    phone_number=phone_number,
                    password=password,
                    full_name=full_name,
                    email=email,
                )
        except IntegrityError as exc:
            # Lost the race to a concurrent registration for the same phone.
            raise UserAlreadyExistsError(phone_number) from exc
        return user.pk

    def set_password(self, phone_number: str, new_password: str) -> int:
        with transaction.atomic():
            try:
                user = User.objects.select_for_update().get(phone_number=phone_number)
            except User.DoesNotExist as exc:
                raise UserNotFoundError(phone_number) from exc
            user.set_password(new_password)
            user.save(update_fields=["password"])
        return user.pk
