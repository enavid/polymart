"""Composition root for the catalog slice.

The only place that wires concrete infrastructure adapters into the use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.catalog.use_cases import (
    CreateAttribute,
    GetAttribute,
    ListAttributes,
)
from src.infrastructure.catalog.repositories import DjangoAttributeRepository
from src.interface.api.audit.container import build_audit_recorder


def build_create_attribute() -> CreateAttribute:
    return CreateAttribute(DjangoAttributeRepository(), build_audit_recorder())


def build_get_attribute() -> GetAttribute:
    return GetAttribute(DjangoAttributeRepository())


def build_list_attributes() -> ListAttributes:
    return ListAttributes(DjangoAttributeRepository())
