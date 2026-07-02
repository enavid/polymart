"""Integration tests for the Django address repository (real DB).

These prove the persistence mapping round-trips, that reads/writes are owner-scoped,
and that default-exclusivity (at most one default per owner) holds both through the
repository's atomic swap and through the database's partial unique constraint.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from src.domain.address.entities import Address
from src.domain.address.exceptions import AddressNotFoundError
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
from src.infrastructure.address.repositories import DjangoAddressRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_FIELDS = {
    "recipient_name": RecipientName("Sara Ahmadi"),
    "phone_number": PhoneNumber("09123456789"),
    "province": Province("Tehran"),
    "city": City("Tehran"),
    "postal_code": PostalCode("1234567890"),
    "line1": AddressLine("Valiasr St, No. 1"),
    "line2": None,
}


def _user(phone: str = "09120000001"):
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _address(owner: str, address_id: str = "ADDR-ABC123", *, is_default: bool = False) -> Address:
    return Address(
        id=AddressId(address_id),
        owner=owner,
        is_default=is_default,
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
        **_FIELDS,
    )


class TestDjangoAddressRepository:
    def test_round_trips_an_address(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()

        saved = repo.add(_address(str(user.pk)))
        reloaded = repo.get_for_owner(str(user.pk), "ADDR-ABC123")

        assert reloaded.id == saved.id
        assert reloaded.recipient_name.value == "Sara Ahmadi"
        assert reloaded.line2 is None

    def test_reads_are_owner_scoped(self) -> None:
        owner = _user("09120000001")
        other = _user("09120000002")
        repo = DjangoAddressRepository()
        repo.add(_address(str(owner.pk)))

        with pytest.raises(AddressNotFoundError):
            repo.get_for_owner(str(other.pk), "ADDR-ABC123")

    def test_a_missing_address_raises_not_found(self) -> None:
        user = _user()
        with pytest.raises(AddressNotFoundError):
            DjangoAddressRepository().get_for_owner(str(user.pk), "ADDR-MISSING0")

    def test_lists_default_first(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()
        repo.add(_address(str(user.pk), "ADDR-FIRST000", is_default=False))
        repo.add(_address(str(user.pk), "ADDR-SECOND00", is_default=True))

        addresses = repo.list_for_owner(str(user.pk))

        assert addresses[0].id.value == "ADDR-SECOND00"
        assert addresses[0].is_default is True

    def test_count_for_owner(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()
        repo.add(_address(str(user.pk), "ADDR-FIRST000"))
        repo.add(_address(str(user.pk), "ADDR-SECOND00"))

        assert repo.count_for_owner(str(user.pk)) == 2

    def test_update_persists_mutable_fields_only(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()
        saved = repo.add(_address(str(user.pk), is_default=True))
        edited = saved.with_details(
            recipient_name=RecipientName("Reza Karimi"),
            phone_number=PhoneNumber("09121112233"),
            province=Province("Fars"),
            city=City("Shiraz"),
            postal_code=PostalCode("9876543210"),
            line1=AddressLine("Zand Blvd"),
            line2=None,
        )

        updated = repo.update(edited)

        assert updated.city.value == "Shiraz"
        assert updated.is_default is True  # unaffected by an edit

    def test_update_of_another_owners_address_raises_not_found(self) -> None:
        owner = _user("09120000001")
        other = _user("09120000002")
        repo = DjangoAddressRepository()
        saved = repo.add(_address(str(owner.pk)))
        forged = replace(saved, owner=str(other.pk))

        with pytest.raises(AddressNotFoundError):
            repo.update(forged)

    def test_delete_removes_the_row(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()
        repo.add(_address(str(user.pk)))

        repo.delete(str(user.pk), "ADDR-ABC123")

        assert repo.count_for_owner(str(user.pk)) == 0

    def test_delete_of_another_owners_address_raises_not_found(self) -> None:
        owner = _user("09120000001")
        other = _user("09120000002")
        repo = DjangoAddressRepository()
        repo.add(_address(str(owner.pk)))

        with pytest.raises(AddressNotFoundError):
            repo.delete(str(other.pk), "ADDR-ABC123")
        assert repo.count_for_owner(str(owner.pk)) == 1

    def test_add_with_default_unsets_the_previous_default(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()
        repo.add(_address(str(user.pk), "ADDR-FIRST000", is_default=True))

        repo.add(_address(str(user.pk), "ADDR-SECOND00", is_default=True))

        first = repo.get_for_owner(str(user.pk), "ADDR-FIRST000")
        second = repo.get_for_owner(str(user.pk), "ADDR-SECOND00")
        assert first.is_default is False
        assert second.is_default is True

    def test_set_default_swaps_exclusively(self) -> None:
        user = _user()
        repo = DjangoAddressRepository()
        repo.add(_address(str(user.pk), "ADDR-FIRST000", is_default=True))
        repo.add(_address(str(user.pk), "ADDR-SECOND00", is_default=False))

        result = repo.set_default(str(user.pk), "ADDR-SECOND00")

        assert result.is_default is True
        assert repo.get_for_owner(str(user.pk), "ADDR-FIRST000").is_default is False

    def test_set_default_of_missing_address_raises_not_found(self) -> None:
        user = _user()
        with pytest.raises(AddressNotFoundError):
            DjangoAddressRepository().set_default(str(user.pk), "ADDR-MISSING0")

    def test_set_default_of_another_owners_address_raises_not_found(self) -> None:
        owner = _user("09120000001")
        other = _user("09120000002")
        repo = DjangoAddressRepository()
        repo.add(_address(str(owner.pk)))

        with pytest.raises(AddressNotFoundError):
            repo.set_default(str(other.pk), "ADDR-ABC123")

    def test_database_enforces_at_most_one_default_per_owner(self) -> None:
        # A defense-in-depth check: bypassing the repository entirely (e.g. a bug in
        # the swap logic) must still be caught by the database's partial unique
        # constraint, not silently allowed.
        user = _user()
        AddressModel.objects.create(
            address_id="ADDR-FIRST000",
            owner_id=user.pk,
            recipient_name="A",
            phone_number="+989123456789",
            province="Tehran",
            city="Tehran",
            postal_code="1234567890",
            line1="L1",
            is_default=True,
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )

        with pytest.raises(IntegrityError):
            AddressModel.objects.create(
                address_id="ADDR-SECOND00",
                owner_id=user.pk,
                recipient_name="B",
                phone_number="+989123456789",
                province="Tehran",
                city="Tehran",
                postal_code="1234567890",
                line1="L1",
                is_default=True,
                created_at=datetime(2026, 7, 2, tzinfo=UTC),
            )
