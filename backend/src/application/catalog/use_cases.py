"""Catalog use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the
domain, side effects (logging, audit) observable.

The catalog schema is white-label configuration: changing it reshapes every
storefront built on it, so each definition mutation emits a structured,
audit-friendly event naming the actor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    AttributeRepository,
    ProductRepository,
    ProductTypeRepository,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, Product, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    InvalidAttributeInputTypeError,
    ProductAlreadyExistsError,
    ProductTypeAlreadyExistsError,
    UnknownAttributeError,
)
from src.domain.catalog.services import normalize_attribute_values
from src.domain.catalog.value_objects import (
    AttributeChoice,
    AttributeCode,
    AttributeValue,
    ProductCode,
    ProductTypeCode,
)

logger = structlog.get_logger(__name__)

# Audit vocabulary for the catalog context. Namespaced ("<resource>.*") so the
# trail stays greppable by area.
_RESOURCE_ATTRIBUTE = "attribute"
_ACTION_ATTRIBUTE_CREATED = "attribute.created"
_RESOURCE_PRODUCT_TYPE = "product_type"
_ACTION_PRODUCT_TYPE_CREATED = "product_type.created"
_RESOURCE_PRODUCT = "product"
_ACTION_PRODUCT_CREATED = "product.created"


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


@dataclass(frozen=True)
class AttributeValueInput:
    """Raw value input for one attribute. Validated/normalized by the domain."""

    attribute: str
    value: str


@dataclass(frozen=True)
class CreateProductCommand:
    """Input for creating a product. Raw strings are validated by the domain."""

    code: str
    name: str
    product_type: str
    values: tuple[AttributeValueInput, ...] = field(default_factory=tuple)
    metadata: Mapping[str, str] = field(default_factory=dict)


class CreateProduct:
    """Create a product whose attribute values conform to its product type.

    The product type and the attribute definitions live in other aggregates, so
    this use case loads them and delegates the conformance rule to the domain
    service; it owns only the orchestration (fetch, validate, persist, observe).
    """

    def __init__(
        self,
        repository: ProductRepository,
        product_types: ProductTypeRepository,
        attributes: AttributeRepository,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._product_types = product_types
        self._attributes = attributes
        self._audit = audit

    def execute(self, command: CreateProductCommand, *, actor: str | None = None) -> Product:
        # Build value objects first: malformed code/name/metadata or a duplicate
        # attribute value fails fast, before any I/O.
        product = Product(
            code=ProductCode(command.code),
            name=command.name,
            product_type=ProductTypeCode(command.product_type),
            values=tuple(
                AttributeValue(attribute=AttributeCode(item.attribute), value=item.value)
                for item in command.values
            ),
            metadata=command.metadata,
        )
        code = product.code.value

        # Resolve the product type and its attribute definitions (in declared
        # order), then let the domain service decide value conformance.
        product_type = self._product_types.get_by_code(product.product_type.value)
        definitions = [
            self._attributes.get_by_code(attribute.value)
            for attribute in product_type.attributes
        ]
        product.values = normalize_attribute_values(definitions, product.values)

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_code(code):
            logger.warning("product_create_rejected_duplicate", code=code, actor=actor)
            raise ProductAlreadyExistsError(code)

        persisted = self._repository.add(product)
        logger.info(
            "product_created",
            product_id=persisted.id,
            code=code,
            product_type=product_type.code.value,
            value_count=len(persisted.values),
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_PRODUCT_CREATED,
            resource_type=_RESOURCE_PRODUCT,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="code", after=code),
                FieldChange(field="product_type", after=product_type.code.value),
                FieldChange(field="value_count", after=len(persisted.values)),
            ),
        )
        return persisted


class GetProduct:
    """Retrieve a single product by code."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def execute(self, *, code: str) -> Product:
        product = self._repository.get_by_code(code)
        logger.debug("product_retrieved", code=code)
        return product


class ListProducts:
    """List every product."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def execute(self) -> list[Product]:
        products = self._repository.list_all()
        logger.debug("products_listed", count=len(products))
        return products
