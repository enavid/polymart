"""Shared seed helpers for the order integration tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.infrastructure.address.models import AddressModel

_DEFAULT_ADDRESS_ID = "ADDR-SHIP000001"


def seed_address(
    owner_pk: int,
    *,
    address_id: str = _DEFAULT_ADDRESS_ID,
    city: str = "Tehran",
) -> str:
    """Create a saved address for the owner and return its public id.

    Checkout captures a snapshot of this address, so the order tests need a real
    address row for the owner they place orders as.
    """
    AddressModel.objects.create(
        address_id=address_id,
        owner_id=owner_pk,
        recipient_name="Sara Ahmadi",
        phone_number="+989123456789",
        province="Tehran",
        city=city,
        postal_code="1234567890",
        line1="Valiasr St, No. 1",
        is_default=True,
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    return address_id
