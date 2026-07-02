"""Composition root for the address slice.

The only place that wires concrete infrastructure adapters into the address use
cases. Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.address.use_cases import (
    AddAddress,
    DeleteAddress,
    ListMyAddresses,
    SetDefaultAddress,
    UpdateAddress,
)
from src.infrastructure.address.clock import SystemClock
from src.infrastructure.address.id_generator import SecureAddressIdGenerator
from src.infrastructure.address.repositories import DjangoAddressRepository
from src.interface.api.audit.container import build_audit_recorder


def build_add_address() -> AddAddress:
    return AddAddress(
        repository=DjangoAddressRepository(),
        ids=SecureAddressIdGenerator(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    )


def build_list_my_addresses() -> ListMyAddresses:
    return ListMyAddresses(DjangoAddressRepository())


def build_update_address() -> UpdateAddress:
    return UpdateAddress(repository=DjangoAddressRepository(), audit=build_audit_recorder())


def build_delete_address() -> DeleteAddress:
    return DeleteAddress(repository=DjangoAddressRepository(), audit=build_audit_recorder())


def build_set_default_address() -> SetDefaultAddress:
    return SetDefaultAddress(repository=DjangoAddressRepository(), audit=build_audit_recorder())
