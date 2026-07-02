"""The Address aggregate: one saved shipping address in a shopper's address book.

Identity is the public ``id`` (opaque, never a sequential database id). The owner is
the stable user id -- an address is always resolved from the authenticated user, never
from a client-supplied id, so cross-user access is impossible. ``is_default`` and
``created_at`` are managed by the application layer (which address is default and when
an address was added are facts about the address book as a whole, not about editing one
address), so ``with_details`` deliberately cannot touch them.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from src.domain.address.value_objects import (
    AddressId,
    AddressLine,
    City,
    PhoneNumber,
    PostalCode,
    Province,
    RecipientName,
)


@dataclass(frozen=True)
class Address:
    """A saved shipping address owned by one shopper."""

    id: AddressId
    owner: str
    recipient_name: RecipientName
    phone_number: PhoneNumber
    province: Province
    city: City
    postal_code: PostalCode
    line1: AddressLine
    line2: AddressLine | None
    is_default: bool
    created_at: datetime

    def with_details(
        self,
        *,
        recipient_name: RecipientName,
        phone_number: PhoneNumber,
        province: Province,
        city: City,
        postal_code: PostalCode,
        line1: AddressLine,
        line2: AddressLine | None,
    ) -> Address:
        """Return a copy with new contact/location details.

        Identity, ownership, default status, and creation time are untouched -- an
        edit changes where a shipment goes, not which address it is or whether it is
        the shopper's default.
        """
        return replace(
            self,
            recipient_name=recipient_name,
            phone_number=phone_number,
            province=province,
            city=city,
            postal_code=postal_code,
            line1=line1,
            line2=line2,
        )
