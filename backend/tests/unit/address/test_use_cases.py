"""Unit tests for the address use cases against fakes (no DB, no framework).

These exercise the orchestration: value-object validation, the per-owner address cap,
first-address-becomes-default, editing without touching identity/default/created_at,
default-swap exclusivity, owner-scoping (no cross-owner reads/writes), and audit
recording.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.address.ports import AddressIdGenerator, AddressRepository, Clock
from src.application.address.use_cases import (
    AddAddress,
    AddAddressCommand,
    DeleteAddress,
    DeleteAddressCommand,
    ListMyAddresses,
    SetDefaultAddress,
    SetDefaultAddressCommand,
    UpdateAddress,
    UpdateAddressCommand,
)
from src.application.audit.ports import AuditRecorder
from src.domain.address.entities import Address
from src.domain.address.exceptions import AddressLimitExceededError, AddressNotFoundError
from src.domain.address.value_objects import AddressId
from src.domain.audit.entities import FieldChange

# --- Fakes -----------------------------------------------------------------


class FakeAddresses(AddressRepository):
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Address] = {}

    def add(self, address: Address) -> Address:
        if address.is_default:
            self._clear_default(address.owner)
        self._by_key[(address.owner, address.id.value)] = address
        return address

    def list_for_owner(self, owner: str) -> tuple[Address, ...]:
        return tuple(a for (own, _), a in self._by_key.items() if own == owner)

    def get_for_owner(self, owner: str, address_id: str) -> Address:
        try:
            return self._by_key[(owner, address_id)]
        except KeyError as exc:
            raise AddressNotFoundError(address_id) from exc

    def update(self, address: Address) -> Address:
        key = (address.owner, address.id.value)
        if key not in self._by_key:
            raise AddressNotFoundError(address.id.value)
        self._by_key[key] = address
        return address

    def delete(self, owner: str, address_id: str) -> None:
        key = (owner, address_id)
        if key not in self._by_key:
            raise AddressNotFoundError(address_id)
        del self._by_key[key]

    def set_default(self, owner: str, address_id: str) -> Address:
        key = (owner, address_id)
        if key not in self._by_key:
            raise AddressNotFoundError(address_id)
        self._clear_default(owner)
        from dataclasses import replace

        updated = replace(self._by_key[key], is_default=True)
        self._by_key[key] = updated
        return updated

    def count_for_owner(self, owner: str) -> int:
        return len(self.list_for_owner(owner))

    def _clear_default(self, owner: str) -> None:
        from dataclasses import replace

        for key, address in list(self._by_key.items()):
            if key[0] == owner and address.is_default:
                self._by_key[key] = replace(address, is_default=False)


class FakeIds(AddressIdGenerator):
    def __init__(self, value: str = "ADDR-TEST01") -> None:
        self._value = value

    def next(self) -> AddressId:
        return AddressId(self._value)


class FixedClock(Clock):
    def now(self) -> datetime:
        return datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: tuple[FieldChange, ...] = (),
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": changes,
            }
        )


_FIELDS = {
    "recipient_name": "Sara Ahmadi",
    "phone_number": "09123456789",
    "province": "Tehran",
    "city": "Tehran",
    "postal_code": "1234567890",
    "line1": "Valiasr St, No. 1",
}


def _add_command(owner: str = "7", **overrides: object) -> AddAddressCommand:
    return AddAddressCommand(owner=owner, **{**_FIELDS, **overrides})


# --- AddAddress --------------------------------------------------------------


class TestAddAddress:
    def test_saves_the_address(self) -> None:
        repository = FakeAddresses()
        add = AddAddress(
            repository=repository, ids=FakeIds(), clock=FixedClock(), audit=RecordingAudit()
        )

        address = add.execute(_add_command())

        assert address.recipient_name.value == "Sara Ahmadi"
        assert address.owner == "7"

    def test_the_first_address_is_always_the_default(self) -> None:
        add = AddAddress(
            repository=FakeAddresses(), ids=FakeIds(), clock=FixedClock(), audit=RecordingAudit()
        )

        address = add.execute(_add_command(is_default=False))

        assert address.is_default is True

    def test_a_second_address_is_not_default_unless_requested(self) -> None:
        repository = FakeAddresses()
        add = AddAddress(
            repository=repository, ids=FakeIds(), clock=FixedClock(), audit=RecordingAudit()
        )
        add.execute(_add_command())

        second = add.execute(AddAddressCommand(owner="7", **{**_FIELDS, "city": "Shiraz"}))

        assert second.is_default is False

    def test_requesting_default_unsets_the_previous_default(self) -> None:
        repository = FakeAddresses()
        add = AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-FIRST0"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        )
        first = add.execute(_add_command())
        assert first.is_default is True

        add2 = AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-SECOND"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        )
        second = add2.execute(
            AddAddressCommand(owner="7", **{**_FIELDS, "city": "Shiraz"}, is_default=True)
        )

        assert second.is_default is True
        refreshed_first = repository.get_for_owner("7", "ADDR-FIRST0")
        assert refreshed_first.is_default is False

    def test_rejects_beyond_the_per_owner_cap(self) -> None:
        repository = FakeAddresses()
        for i in range(20):
            add = AddAddress(
                repository=repository,
                ids=FakeIds(f"ADDR-N{i:04d}"),
                clock=FixedClock(),
                audit=RecordingAudit(),
            )
            add.execute(_add_command())

        overflow = AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-N9999"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        )
        with pytest.raises(AddressLimitExceededError):
            overflow.execute(_add_command())

    def test_rejects_invalid_fields_before_any_write(self) -> None:
        repository = FakeAddresses()
        add = AddAddress(
            repository=repository, ids=FakeIds(), clock=FixedClock(), audit=RecordingAudit()
        )

        with pytest.raises(Exception):  # noqa: B017 -- domain raises a specific subtype
            add.execute(_add_command(postal_code="not-a-postal-code"))
        assert repository.count_for_owner("7") == 0

    def test_audits_the_creation(self) -> None:
        audit = RecordingAudit()
        add = AddAddress(repository=FakeAddresses(), ids=FakeIds(), clock=FixedClock(), audit=audit)

        add.execute(_add_command())

        record = audit.records[-1]
        assert record["action"] == "address.created"
        assert record["resource_type"] == "address"
        assert record["resource_id"] == "ADDR-TEST01"
        assert record["actor"] == "7"


# --- ListMyAddresses -----------------------------------------------------


class TestListMyAddresses:
    def test_lists_only_the_owners_addresses(self) -> None:
        repository = FakeAddresses()
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-OWNER0"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command(owner="7"))
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-OTHER0"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command(owner="8"))

        addresses = ListMyAddresses(repository).execute("7")

        assert len(addresses) == 1
        assert addresses[0].owner == "7"


# --- UpdateAddress -----------------------------------------------------


class TestUpdateAddress:
    def _seed(self, repository: FakeAddresses) -> Address:
        return AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-TEST01"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command())

    def test_updates_the_contact_details(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        update = UpdateAddress(repository=repository, audit=RecordingAudit())

        updated = update.execute(
            UpdateAddressCommand(
                owner="7",
                address_id="ADDR-TEST01",
                **{**_FIELDS, "city": "Shiraz"},
            )
        )

        assert updated.city.value == "Shiraz"

    def test_never_changes_default_status(self) -> None:
        repository = FakeAddresses()
        original = self._seed(repository)
        assert original.is_default is True
        update = UpdateAddress(repository=repository, audit=RecordingAudit())

        updated = update.execute(
            UpdateAddressCommand(owner="7", address_id="ADDR-TEST01", **_FIELDS)
        )

        assert updated.is_default is True

    def test_another_owner_cannot_update_it(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        update = UpdateAddress(repository=repository, audit=RecordingAudit())

        with pytest.raises(AddressNotFoundError):
            update.execute(UpdateAddressCommand(owner="8", address_id="ADDR-TEST01", **_FIELDS))

    def test_audits_the_update(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        audit = RecordingAudit()
        update = UpdateAddress(repository=repository, audit=audit)

        update.execute(
            UpdateAddressCommand(
                owner="7", address_id="ADDR-TEST01", **{**_FIELDS, "city": "Shiraz"}
            )
        )

        assert audit.records[-1]["action"] == "address.updated"

    def test_audits_only_the_fields_that_actually_changed(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        audit = RecordingAudit()
        update = UpdateAddress(repository=repository, audit=audit)

        update.execute(
            UpdateAddressCommand(
                owner="7", address_id="ADDR-TEST01", **{**_FIELDS, "city": "Shiraz"}
            )
        )

        changes = audit.records[-1]["changes"]
        fields = {change.field: (change.before, change.after) for change in changes}
        assert fields == {"city": ("Tehran", "Shiraz")}

    def test_audits_every_field_that_changed_when_several_change_at_once(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        audit = RecordingAudit()
        update = UpdateAddress(repository=repository, audit=audit)

        update.execute(
            UpdateAddressCommand(
                owner="7",
                address_id="ADDR-TEST01",
                **{**_FIELDS, "city": "Shiraz", "phone_number": "09121112233"},
            )
        )

        changes = audit.records[-1]["changes"]
        fields = {change.field for change in changes}
        assert fields == {"city", "phone_number"}

    def test_a_no_op_update_does_not_audit(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        audit = RecordingAudit()
        update = UpdateAddress(repository=repository, audit=audit)

        update.execute(UpdateAddressCommand(owner="7", address_id="ADDR-TEST01", **_FIELDS))

        assert audit.records == []


# --- DeleteAddress -----------------------------------------------------


class TestDeleteAddress:
    def _seed(self, repository: FakeAddresses) -> None:
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-TEST01"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command())

    def test_deletes_the_address(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        delete = DeleteAddress(repository=repository, audit=RecordingAudit())

        delete.execute(DeleteAddressCommand(owner="7", address_id="ADDR-TEST01"))

        assert repository.count_for_owner("7") == 0

    def test_another_owner_cannot_delete_it(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        delete = DeleteAddress(repository=repository, audit=RecordingAudit())

        with pytest.raises(AddressNotFoundError):
            delete.execute(DeleteAddressCommand(owner="8", address_id="ADDR-TEST01"))
        assert repository.count_for_owner("7") == 1

    def test_audits_the_deletion(self) -> None:
        repository = FakeAddresses()
        self._seed(repository)
        audit = RecordingAudit()
        delete = DeleteAddress(repository=repository, audit=audit)

        delete.execute(DeleteAddressCommand(owner="7", address_id="ADDR-TEST01"))

        assert audit.records[-1]["action"] == "address.deleted"


# --- SetDefaultAddress -----------------------------------------------------


class TestSetDefaultAddress:
    def test_makes_the_address_the_sole_default(self) -> None:
        repository = FakeAddresses()
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-FIRST0"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command())
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-SECOND"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(AddAddressCommand(owner="7", **{**_FIELDS, "city": "Shiraz"}))

        set_default = SetDefaultAddress(repository=repository, audit=RecordingAudit())
        result = set_default.execute(SetDefaultAddressCommand(owner="7", address_id="ADDR-SECOND"))

        assert result.is_default is True
        first = repository.get_for_owner("7", "ADDR-FIRST0")
        assert first.is_default is False

    def test_another_owner_cannot_set_it_default(self) -> None:
        repository = FakeAddresses()
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-TEST01"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command())

        set_default = SetDefaultAddress(repository=repository, audit=RecordingAudit())
        with pytest.raises(AddressNotFoundError):
            set_default.execute(SetDefaultAddressCommand(owner="8", address_id="ADDR-TEST01"))

    def test_audits_the_default_change(self) -> None:
        repository = FakeAddresses()
        AddAddress(
            repository=repository,
            ids=FakeIds("ADDR-TEST01"),
            clock=FixedClock(),
            audit=RecordingAudit(),
        ).execute(_add_command())
        audit = RecordingAudit()
        set_default = SetDefaultAddress(repository=repository, audit=audit)

        set_default.execute(SetDefaultAddressCommand(owner="7", address_id="ADDR-TEST01"))

        assert audit.records[-1]["action"] == "address.default_changed"
