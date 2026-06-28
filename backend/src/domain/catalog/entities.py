"""The Attribute entity: a reusable, typed property definition.

An attribute is the unit of the platform's flexible, white-label data model: it
declares a named, typed property (roast level, origin, weight, ...) that product
types later compose. The rules that make a definition coherent -- a name, and
choices that match the input type -- live here, in pure Python.

No Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeChoicesNotAllowedError,
    AttributeChoicesRequiredError,
    DuplicateAttributeAssignmentError,
    DuplicateAttributeChoiceError,
    InvalidAttributeNameError,
    InvalidProductTypeNameError,
)
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode, ProductTypeCode

_NAME_MAX_LENGTH = 255


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
