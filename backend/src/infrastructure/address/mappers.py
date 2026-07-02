"""Mapping between the Address domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.address.entities import Address
from src.domain.address.value_objects import (
    AddressId,
    AddressLine,
    City,
    PhoneNumber,
    PostalCode,
    Province,
    RecipientName,
)
from src.infrastructure.address.models import AddressModel


def address_to_domain(model: AddressModel) -> Address:
    """Rebuild the aggregate from a persisted address row.

    The owner is stringified so the domain owns a stable id independent of the
    database's integer key type.
    """
    return Address(
        id=AddressId(model.address_id),
        owner=str(model.owner_id),
        recipient_name=RecipientName(model.recipient_name),
        phone_number=PhoneNumber(model.phone_number),
        province=Province(model.province),
        city=City(model.city),
        postal_code=PostalCode(model.postal_code),
        line1=AddressLine(model.line1),
        line2=AddressLine(model.line2) if model.line2 else None,
        is_default=model.is_default,
        created_at=model.created_at,
    )
