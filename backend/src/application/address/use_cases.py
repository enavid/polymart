"""Address-book use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the domain,
side effects (logging, audit) observable. Every mutation is recorded on the durable
audit trail -- audit is not reserved for money/inventory paths in this codebase (see
the catalog context's attribute/category/collection use cases for the same pattern).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.address.ports import AddressIdGenerator, AddressRepository, Clock
from src.application.audit.ports import AuditRecorder
from src.domain.address.entities import Address
from src.domain.address.exceptions import AddressLimitExceededError
from src.domain.address.value_objects import (
    AddressId,
    AddressLine,
    City,
    PhoneNumber,
    PostalCode,
    Province,
    RecipientName,
)
from src.domain.audit.entities import FieldChange

logger = structlog.get_logger(__name__)

# A defensive cap against unbounded growth (not a business requirement) -- an address
# book is a short, curated list, not an unbounded data store.
_MAX_ADDRESSES_PER_OWNER = 20

_RESOURCE_ADDRESS = "address"
_ACTION_ADDRESS_CREATED = "address.created"
_ACTION_ADDRESS_UPDATED = "address.updated"
_ACTION_ADDRESS_DELETED = "address.deleted"
_ACTION_ADDRESS_DEFAULT_CHANGED = "address.default_changed"


@dataclass(frozen=True)
class AddAddressCommand:
    """Input for saving a new address to the owner's address book."""

    owner: str
    recipient_name: str
    phone_number: str
    province: str
    city: str
    postal_code: str
    line1: str
    line2: str | None = None
    is_default: bool = False


class AddAddress:
    """Save a new address, becoming the owner's default if it is their first."""

    def __init__(
        self,
        *,
        repository: AddressRepository,
        ids: AddressIdGenerator,
        clock: Clock,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._ids = ids
        self._clock = clock
        self._audit = audit

    def execute(self, command: AddAddressCommand) -> Address:
        # Build value objects first: invalid input fails fast, before any I/O.
        recipient_name = RecipientName(command.recipient_name)
        phone_number = PhoneNumber(command.phone_number)
        province = Province(command.province)
        city = City(command.city)
        postal_code = PostalCode(command.postal_code)
        line1 = AddressLine(command.line1)
        line2 = AddressLine(command.line2) if command.line2 else None

        count = self._repository.count_for_owner(command.owner)
        if count >= _MAX_ADDRESSES_PER_OWNER:
            raise AddressLimitExceededError(command.owner, _MAX_ADDRESSES_PER_OWNER)

        address = Address(
            id=self._ids.next(),
            owner=command.owner,
            recipient_name=recipient_name,
            phone_number=phone_number,
            province=province,
            city=city,
            postal_code=postal_code,
            line1=line1,
            line2=line2,
            # An owner's very first address is always their default -- an address
            # book with addresses but no default would leave checkout with nothing
            # to preselect.
            is_default=(count == 0) or command.is_default,
            created_at=self._clock.now(),
        )
        saved = self._repository.add(address)
        self._audit.record(
            action=_ACTION_ADDRESS_CREATED,
            resource_type=_RESOURCE_ADDRESS,
            resource_id=saved.id.value,
            actor=command.owner,
            changes=(
                FieldChange(field="city", after=saved.city.value),
                FieldChange(field="is_default", after=saved.is_default),
            ),
        )
        logger.info(
            "address_created",
            owner=command.owner,
            address_id=saved.id.value,
            is_default=saved.is_default,
        )
        return saved


class ListMyAddresses:
    """List the authenticated shopper's own saved addresses."""

    def __init__(self, repository: AddressRepository) -> None:
        self._repository = repository

    def execute(self, owner: str) -> tuple[Address, ...]:
        addresses = self._repository.list_for_owner(owner)
        logger.debug("addresses_listed", owner=owner, count=len(addresses))
        return addresses


@dataclass(frozen=True)
class UpdateAddressCommand:
    """Input for editing an existing address's contact/location details."""

    owner: str
    address_id: str
    recipient_name: str
    phone_number: str
    province: str
    city: str
    postal_code: str
    line1: str
    line2: str | None = None


class UpdateAddress:
    """Edit an existing address's details (never its id, owner, or default status)."""

    def __init__(self, *, repository: AddressRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(self, command: UpdateAddressCommand) -> Address:
        canonical = AddressId(command.address_id).value
        current = self._repository.get_for_owner(command.owner, canonical)
        updated = current.with_details(
            recipient_name=RecipientName(command.recipient_name),
            phone_number=PhoneNumber(command.phone_number),
            province=Province(command.province),
            city=City(command.city),
            postal_code=PostalCode(command.postal_code),
            line1=AddressLine(command.line1),
            line2=AddressLine(command.line2) if command.line2 else None,
        )
        saved = self._repository.update(updated)
        changes = _changed_fields(current, saved)
        # A no-op edit (resubmitting identical details) records nothing, matching
        # every other context's audit trail in this codebase.
        if changes:
            self._audit.record(
                action=_ACTION_ADDRESS_UPDATED,
                resource_type=_RESOURCE_ADDRESS,
                resource_id=canonical,
                actor=command.owner,
                changes=changes,
            )
        logger.info("address_updated", owner=command.owner, address_id=canonical)
        return saved


def _changed_fields(before: Address, after: Address) -> tuple[FieldChange, ...]:
    """Return one FieldChange per contact/location field that actually changed.

    An edit can touch several fields at once (unlike a single-field toggle), so the
    audit trail must record exactly what changed rather than a single fixed field --
    an address's recipient/phone/location are all security-relevant for a shipment,
    and a misleading "city changed" entry when only the phone number moved would
    undermine an investigation.
    """
    line2_before = before.line2.value if before.line2 else None
    line2_after = after.line2.value if after.line2 else None
    candidates = (
        ("recipient_name", before.recipient_name.value, after.recipient_name.value),
        ("phone_number", before.phone_number.value, after.phone_number.value),
        ("province", before.province.value, after.province.value),
        ("city", before.city.value, after.city.value),
        ("postal_code", before.postal_code.value, after.postal_code.value),
        ("line1", before.line1.value, after.line1.value),
        ("line2", line2_before, line2_after),
    )
    return tuple(
        FieldChange(field=field, before=old, after=new)
        for field, old, new in candidates
        if old != new
    )


@dataclass(frozen=True)
class DeleteAddressCommand:
    """Input for removing an address from the owner's address book."""

    owner: str
    address_id: str


class DeleteAddress:
    """Remove an address from the owner's address book."""

    def __init__(self, *, repository: AddressRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(self, command: DeleteAddressCommand) -> None:
        canonical = AddressId(command.address_id).value
        current = self._repository.get_for_owner(command.owner, canonical)
        self._repository.delete(command.owner, canonical)
        self._audit.record(
            action=_ACTION_ADDRESS_DELETED,
            resource_type=_RESOURCE_ADDRESS,
            resource_id=canonical,
            actor=command.owner,
            changes=(FieldChange(field="city", before=current.city.value),),
        )
        logger.info("address_deleted", owner=command.owner, address_id=canonical)


@dataclass(frozen=True)
class SetDefaultAddressCommand:
    """Input for marking one of the owner's addresses as their default."""

    owner: str
    address_id: str


class SetDefaultAddress:
    """Make one address the owner's sole default, atomically unsetting any other."""

    def __init__(self, *, repository: AddressRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(self, command: SetDefaultAddressCommand) -> Address:
        canonical = AddressId(command.address_id).value
        saved = self._repository.set_default(command.owner, canonical)
        self._audit.record(
            action=_ACTION_ADDRESS_DEFAULT_CHANGED,
            resource_type=_RESOURCE_ADDRESS,
            resource_id=canonical,
            actor=command.owner,
            changes=(FieldChange(field="is_default", before=False, after=True),),
        )
        logger.info("address_default_changed", owner=command.owner, address_id=canonical)
        return saved
