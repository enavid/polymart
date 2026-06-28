"""Catalog use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the
domain, side effects (logging, audit) observable.

The catalog schema is white-label configuration: changing it reshapes every
storefront built on it, so each definition mutation emits a structured,
audit-friendly event naming the actor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import AttributeRepository
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    InvalidAttributeInputTypeError,
)
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode

logger = structlog.get_logger(__name__)

# Audit vocabulary for the catalog context. Namespaced ("attribute.*") so the
# trail stays greppable by area.
_RESOURCE_ATTRIBUTE = "attribute"
_ACTION_ATTRIBUTE_CREATED = "attribute.created"


@dataclass(frozen=True)
class AttributeChoiceInput:
    """Raw choice input. Validated into an ``AttributeChoice`` by the domain."""

    value: str
    label: str


@dataclass(frozen=True)
class CreateAttributeCommand:
    """Input for creating an attribute. Raw strings are validated by the domain."""

    code: str
    name: str
    input_type: str
    required: bool = False
    choices: tuple[AttributeChoiceInput, ...] = field(default_factory=tuple)


def _to_input_type(raw: str) -> AttributeInputType:
    """Resolve a raw string to the enum, as a domain error if it is unknown."""
    try:
        return AttributeInputType(raw)
    except ValueError as exc:
        raise InvalidAttributeInputTypeError(raw) from exc


class CreateAttribute:
    """Register a new dynamic attribute definition."""

    def __init__(self, repository: AttributeRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(self, command: CreateAttributeCommand, *, actor: str | None = None) -> Attribute:
        # Build value objects first: invalid input fails fast, before any I/O.
        attribute = Attribute(
            code=AttributeCode(command.code),
            name=command.name,
            input_type=_to_input_type(command.input_type),
            required=command.required,
            choices=tuple(
                AttributeChoice(value=choice.value, label=choice.label)
                for choice in command.choices
            ),
        )
        code = attribute.code.value

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_code(code):
            logger.warning("attribute_create_rejected_duplicate", code=code, actor=actor)
            raise AttributeAlreadyExistsError(code)

        persisted = self._repository.add(attribute)
        logger.info(
            "attribute_created",
            attribute_id=persisted.id,
            code=code,
            input_type=persisted.input_type.value,
            required=persisted.required,
            choice_count=len(persisted.choices),
            actor=actor,
        )
        # Durable audit trail (creation has only "after" values).
        self._audit.record(
            action=_ACTION_ATTRIBUTE_CREATED,
            resource_type=_RESOURCE_ATTRIBUTE,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="code", after=code),
                FieldChange(field="input_type", after=persisted.input_type.value),
                FieldChange(field="required", after=persisted.required),
                FieldChange(field="choice_count", after=len(persisted.choices)),
            ),
        )
        return persisted


class GetAttribute:
    """Retrieve a single attribute by code."""

    def __init__(self, repository: AttributeRepository) -> None:
        self._repository = repository

    def execute(self, *, code: str) -> Attribute:
        attribute = self._repository.get_by_code(code)
        logger.debug("attribute_retrieved", code=code)
        return attribute


class ListAttributes:
    """List every attribute definition."""

    def __init__(self, repository: AttributeRepository) -> None:
        self._repository = repository

    def execute(self) -> list[Attribute]:
        attributes = self._repository.list_all()
        logger.debug("attributes_listed", count=len(attributes))
        return attributes
