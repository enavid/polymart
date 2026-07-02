"""Unit tests for the Address aggregate (pure, no framework)."""

from __future__ import annotations

from datetime import UTC, datetime

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


def _address(*, is_default: bool = False, line2: AddressLine | None = None) -> Address:
    return Address(
        id=AddressId("ADDR-ABC123"),
        owner="7",
        recipient_name=RecipientName("Sara Ahmadi"),
        phone_number=PhoneNumber("09123456789"),
        province=Province("Tehran"),
        city=City("Tehran"),
        postal_code=PostalCode("1234567890"),
        line1=AddressLine("Valiasr St, No. 1"),
        line2=line2,
        is_default=is_default,
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


class TestAddress:
    def test_builds_with_no_line2(self) -> None:
        address = _address()
        assert address.line2 is None

    def test_builds_with_a_line2(self) -> None:
        address = _address(line2=AddressLine("Unit 4"))
        assert address.line2 is not None
        assert address.line2.value == "Unit 4"


class TestWithDetails:
    def test_returns_a_new_instance_with_updated_fields(self) -> None:
        original = _address()
        updated = original.with_details(
            recipient_name=RecipientName("Reza Karimi"),
            phone_number=PhoneNumber("09121112233"),
            province=Province("Fars"),
            city=City("Shiraz"),
            postal_code=PostalCode("9876543210"),
            line1=AddressLine("Zand Blvd"),
            line2=None,
        )

        assert updated is not original
        assert updated.recipient_name.value == "Reza Karimi"
        assert updated.city.value == "Shiraz"

    def test_never_changes_identity_owner_default_or_created_at(self) -> None:
        original = _address(is_default=True)
        updated = original.with_details(
            recipient_name=RecipientName("Reza Karimi"),
            phone_number=PhoneNumber("09121112233"),
            province=Province("Fars"),
            city=City("Shiraz"),
            postal_code=PostalCode("9876543210"),
            line1=AddressLine("Zand Blvd"),
            line2=None,
        )

        assert updated.id == original.id
        assert updated.owner == original.owner
        assert updated.is_default == original.is_default
        assert updated.created_at == original.created_at
