"""The Attribute entity: a reusable, typed property definition.

An attribute is the unit of the platform's flexible, white-label data model: it
declares a named, typed property (roast level, origin, weight, ...) that product
types later compose. The rules that make a definition coherent -- a name, and
choices that match the input type -- live here, in pure Python.

No Django, no DRF, no ORM.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeChoicesNotAllowedError,
    AttributeChoicesRequiredError,
    DuplicateAttributeAssignmentError,
    DuplicateAttributeChoiceError,
    DuplicateAttributeValueError,
    InvalidAttributeNameError,
    InvalidProductMetadataError,
    InvalidProductNameError,
    InvalidProductTypeNameError,
)
from src.domain.catalog.value_objects import (
    AttributeChoice,
    AttributeCode,
    AttributeValue,
    ProductCode,
    ProductTypeCode,
)

_NAME_MAX_LENGTH = 255
_METADATA_KEY_MAX_LENGTH = 64
_METADATA_VALUE_MAX_LENGTH = 1024


@dataclass
class Attribute:
    """A dynamic attribute definition.

    Identity is the database ``id`` once persisted, but the ``code`` is the stable
    business key used everywhere in the API.
    """

    code: AttributeCode
    name: str
    input_type: AttributeInputType
    required: bool = False
    choices: tuple[AttributeChoice, ...] = ()
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.choices = self._validated_choices(self.choices)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidAttributeNameError(raw)
        return name

    def _validated_choices(
        self, choices: tuple[AttributeChoice, ...]
    ) -> tuple[AttributeChoice, ...]:
        choices = tuple(choices)
        if self.input_type.is_choice_type:
            if not choices:
                raise AttributeChoicesRequiredError(self.input_type.value)
        elif choices:
            raise AttributeChoicesNotAllowedError(self.input_type.value)
        self._reject_duplicate_values(choices)
        return choices

    @staticmethod
    def _reject_duplicate_values(choices: tuple[AttributeChoice, ...]) -> None:
        seen: set[str] = set()
        for choice in choices:
            if choice.value in seen:
                raise DuplicateAttributeChoiceError(choice.value)
            seen.add(choice.value)


@dataclass
class ProductType:
    """A named template that assigns a set of attributes to its products.

    The product type references attributes by code (it does not own them) in a
    stable display order, and never references the same attribute twice. Whether
    each referenced attribute actually exists is an application-layer concern
    (validated against the attribute repository), since the entity cannot reach
    persistence.
    """

    code: ProductTypeCode
    name: str
    attributes: tuple[AttributeCode, ...] = ()
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.attributes = self._validated_attributes(self.attributes)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidProductTypeNameError(raw)
        return name

    @staticmethod
    def _validated_attributes(
        attributes: tuple[AttributeCode, ...],
    ) -> tuple[AttributeCode, ...]:
        attributes = tuple(attributes)
        seen: set[str] = set()
        for attribute in attributes:
            if attribute.value in seen:
                raise DuplicateAttributeAssignmentError(attribute.value)
            seen.add(attribute.value)
        return attributes


@dataclass
class Product:
    """A sellable item built on a product type, carrying its attribute values.

    The product references its product type by code and supplies a value for some
    or all of that type's attributes. This entity owns only *structural* rules: a
    name, at most one value per attribute, and well-formed metadata. Whether each
    value conforms to its attribute's input type (and whether required attributes
    are present) is a cross-aggregate rule decided by the conformance domain
    service, which has the attribute definitions the entity cannot reach.

    ``metadata`` is free-form, string-keyed, string-valued extension data (mirroring
    Saleor's metadata) -- never a place for money, which is modelled with Decimal in
    the pricing slice.
    """

    code: ProductCode
    name: str
    product_type: ProductTypeCode
    values: tuple[AttributeValue, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.values = self._validated_values(self.values)
        self.metadata = self._validated_metadata(self.metadata)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidProductNameError(raw)
        return name

    @staticmethod
    def _validated_values(
        values: tuple[AttributeValue, ...],
    ) -> tuple[AttributeValue, ...]:
        values = tuple(values)
        seen: set[str] = set()
        for value in values:
            code = value.attribute.value
            if code in seen:
                raise DuplicateAttributeValueError(code)
            seen.add(code)
        return values

    @staticmethod
    def _validated_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        for key, value in metadata.items():
            stripped_key = key.strip()
            if not stripped_key or len(stripped_key) > _METADATA_KEY_MAX_LENGTH:
                raise InvalidProductMetadataError(f"key {key!r}")
            if len(value) > _METADATA_VALUE_MAX_LENGTH:
                raise InvalidProductMetadataError(f"value for key {stripped_key!r}")
            validated[stripped_key] = value
        return validated
