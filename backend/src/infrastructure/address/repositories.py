"""Django ORM implementation of the address repository port.

All reads are owner-scoped, so one shopper can never reach another's address. Default
exclusivity (at most one default per owner) is enforced both here (atomically, with a
row lock on the swap target) and by the database's partial unique constraint, which
backstops the application-level swap against any bug in this layer.
"""

from __future__ import annotations

from django.db import transaction

from src.application.address.ports import AddressRepository
from src.domain.address.entities import Address
from src.domain.address.exceptions import AddressNotFoundError
from src.infrastructure.address.mappers import address_to_domain
from src.infrastructure.address.models import AddressModel


def _owner_pk(owner: str) -> int:
    """Translate the domain's string owner id back to the user's integer primary key."""
    return int(owner)


class DjangoAddressRepository(AddressRepository):
    """Persist addresses with the Django ORM, returning domain aggregates."""

    def add(self, address: Address) -> Address:
        with transaction.atomic():
            if address.is_default:
                self._clear_default(address.owner)
            model = AddressModel.objects.create(
                address_id=address.id.value,
                owner_id=_owner_pk(address.owner),
                recipient_name=address.recipient_name.value,
                phone_number=address.phone_number.value,
                province=address.province.value,
                city=address.city.value,
                postal_code=address.postal_code.value,
                line1=address.line1.value,
                line2=address.line2.value if address.line2 else "",
                is_default=address.is_default,
                created_at=address.created_at,
            )
        return address_to_domain(model)

    def list_for_owner(self, owner: str) -> tuple[Address, ...]:
        rows = AddressModel.objects.filter(owner_id=_owner_pk(owner))
        return tuple(address_to_domain(row) for row in rows)

    def get_for_owner(self, owner: str, address_id: str) -> Address:
        try:
            model = AddressModel.objects.get(address_id=address_id, owner_id=_owner_pk(owner))
        except AddressModel.DoesNotExist as exc:
            raise AddressNotFoundError(address_id) from exc
        return address_to_domain(model)

    def update(self, address: Address) -> Address:
        updated = AddressModel.objects.filter(
            address_id=address.id.value, owner_id=_owner_pk(address.owner)
        ).update(
            recipient_name=address.recipient_name.value,
            phone_number=address.phone_number.value,
            province=address.province.value,
            city=address.city.value,
            postal_code=address.postal_code.value,
            line1=address.line1.value,
            line2=address.line2.value if address.line2 else "",
        )
        if updated == 0:
            raise AddressNotFoundError(address.id.value)
        return self.get_for_owner(address.owner, address.id.value)

    def delete(self, owner: str, address_id: str) -> None:
        deleted, _ = AddressModel.objects.filter(
            address_id=address_id, owner_id=_owner_pk(owner)
        ).delete()
        if deleted == 0:
            raise AddressNotFoundError(address_id)

    def set_default(self, owner: str, address_id: str) -> Address:
        with transaction.atomic():
            try:
                # Lock the swap target so two concurrent "make this my default"
                # requests for the same address serialize instead of racing.
                target = AddressModel.objects.select_for_update().get(
                    address_id=address_id, owner_id=_owner_pk(owner)
                )
            except AddressModel.DoesNotExist as exc:
                raise AddressNotFoundError(address_id) from exc
            AddressModel.objects.filter(owner_id=_owner_pk(owner), is_default=True).exclude(
                pk=target.pk
            ).update(is_default=False)
            if not target.is_default:
                target.is_default = True
                target.save(update_fields=["is_default"])
        return address_to_domain(target)

    def count_for_owner(self, owner: str) -> int:
        return AddressModel.objects.filter(owner_id=_owner_pk(owner)).count()

    @staticmethod
    def _clear_default(owner: str) -> None:
        AddressModel.objects.filter(owner_id=_owner_pk(owner), is_default=True).update(
            is_default=False
        )
