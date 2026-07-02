"""Django ORM implementation of the UserDirectory port.

Bridges the OTP use cases to the custom user model, translating ORM-specific
failures into domain exceptions so the application layer never sees a framework
leak. Returns plain ids, never ORM instances.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from src.application.identity.ports import UserAccount, UserDirectory
from src.domain.identity.exceptions import UserAlreadyExistsError, UserNotFoundError
from src.infrastructure.identity.models import User


def _to_account(user: User) -> UserAccount:
    """Project the ORM user to the framework-free administration read shape."""
    return UserAccount(
        id=user.pk,
        phone_number=user.phone_number,
        full_name=user.full_name,
        email=user.email,
        is_staff=user.is_staff,
        is_active=user.is_active,
    )


class DjangoUserDirectory(UserDirectory):
    """Account lookups and mutations backed by the ``User`` model."""

    def exists(self, phone_number: str) -> bool:
        return User.objects.filter(phone_number=phone_number).exists()

    def create(
        self,
        phone_number: str,
        *,
        password: str,
        full_name: str,
        email: str,
        is_staff: bool = False,
    ) -> int:
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    phone_number=phone_number,
                    password=password,
                    full_name=full_name,
                    email=email,
                    is_staff=is_staff,
                )
        except IntegrityError as exc:
            # Lost the race to a concurrent registration for the same phone.
            raise UserAlreadyExistsError(phone_number) from exc
        return user.pk

    def list_accounts(self, *, limit: int, offset: int) -> tuple[tuple[UserAccount, ...], int]:
        queryset = User.objects.all().order_by("id")
        total = queryset.count()
        window = queryset[offset : offset + limit]
        return tuple(_to_account(user) for user in window), total

    def get_account(self, user_id: int) -> UserAccount:
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist as exc:
            raise UserNotFoundError(str(user_id)) from exc
        return _to_account(user)

    def set_password(self, phone_number: str, new_password: str) -> int:
        with transaction.atomic():
            try:
                user = User.objects.select_for_update().get(phone_number=phone_number)
            except User.DoesNotExist as exc:
                raise UserNotFoundError(phone_number) from exc
            user.set_password(new_password)
            user.save(update_fields=["password"])
        return user.pk
