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
from src.application.catalog.ports import AttributeRepository, ProductTypeRepository
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    InvalidAttributeInputTypeError,
    ProductTypeAlreadyExistsError,
    UnknownAttributeError,
)
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode, ProductTypeCode

logger = structlog.get_logger(__name__)

# Audit vocabulary for the catalog context. Namespaced ("<resource>.*") so the
# trail stays greppable by area.
_RESOURCE_ATTRIBUTE = "attribute"
_ACTION_ATTRIBUTE_CREATED = "attribute.created"
_RESOURCE_PRODUCT_TYPE = "product_type"
_ACTION_PRODUCT_TYPE_CREATED = "product_type.created"


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


@dataclass(frozen=True)
class CreateProductTypeCommand:
    """Input for creating a product type. Raw strings are validated by the domain."""

    code: str
    name: str
    attributes: tuple[str, ...] = field(default_factory=tuple)


class CreateProductType:
    """Register a new product type that assigns a set of attributes."""

    def __init__(
        self,
        repository: ProductTypeRepository,
        attributes: AttributeRepository,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._attributes = attributes
        self._audit = audit

    def execute(
        self, command: CreateProductTypeCommand, *, actor: str | None = None
    ) -> ProductType:
        # Build value objects first: invalid input (codes, name, duplicate refs)
        # fails fast, before any I/O.
        product_type = ProductType(
            code=ProductTypeCode(command.code),
            name=command.name,
            attributes=tuple(AttributeCode(code) for code in command.attributes),
        )
        code = product_type.code.value

        self._reject_unknown_attributes(product_type.attributes, actor=actor)

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_code(code):
            logger.warning("product_type_create_rejected_duplicate", code=code, actor=actor)
            raise ProductTypeAlreadyExistsError(code)

        persisted = self._repository.add(product_type)
        logger.info(
            "product_type_created",
            product_type_id=persisted.id,
            code=code,
            attribute_count=len(persisted.attributes),
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_PRODUCT_TYPE_CREATED,
            resource_type=_RESOURCE_PRODUCT_TYPE,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="code", after=code),
                FieldChange(field="attribute_count", after=len(persisted.attributes)),
            ),
        )
        return persisted

    def _reject_unknown_attributes(
        self, attributes: tuple[AttributeCode, ...], *, actor: str | None
    ) -> None:
        for attribute in attributes:
            if not self._attributes.exists_by_code(attribute.value):
                logger.warning(
                    "product_type_create_rejected_unknown_attribute",
                    attribute=attribute.value,
                    actor=actor,
                )
                raise UnknownAttributeError(attribute.value)


class GetProductType:
    """Retrieve a single product type by code."""

    def __init__(self, repository: ProductTypeRepository) -> None:
        self._repository = repository

    def execute(self, *, code: str) -> ProductType:
        product_type = self._repository.get_by_code(code)
        logger.debug("product_type_retrieved", code=code)
        return product_type


class ListProductTypes:
    """List every product type."""

    def __init__(self, repository: ProductTypeRepository) -> None:
        self._repository = repository

    def execute(self) -> list[ProductType]:
        product_types = self._repository.list_all()
        logger.debug("product_types_listed", count=len(product_types))
        return product_types
