"""Value objects for the catalog context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state. They carry no identity -- equality is by value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.catalog.exceptions import (
    InvalidAttributeChoiceError,
    InvalidAttributeCodeError,
    InvalidProductCodeError,
    InvalidProductTypeCodeError,
)

# URL-safe kebab-case: lower-case alphanumerics in hyphen-separated groups. Codes
# are stable machine keys (e.g. "roast-level"), so the format is intentionally
# strict and shared by attribute codes and choice values.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_MAX_LENGTH = 64
_LABEL_MAX_LENGTH = 255


@dataclass(frozen=True)
class AttributeCode:
    """A stable, URL-safe identifier for a dynamic attribute."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidAttributeCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductTypeCode:
    """A stable, URL-safe identifier for a product type."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidProductTypeCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductCode:
    """A stable, URL-safe identifier for a product."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidProductCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AttributeValue:
    """A product's value for one attribute, keyed by the attribute's code.

    The ``value`` is the canonical string form (a number, a boolean literal, a
    choice slug, or free text). Whether it conforms to the attribute's input type
    is decided by the conformance domain service, which has the definition; the
    value object only pairs a code with its stored string.
    """

    attribute: AttributeCode
    value: str


@dataclass(frozen=True)
class AttributeChoice:
    """One allowed option of a choice-type attribute.

    ``value`` is a stable slug (the machine key persisted with each product),
    while ``label`` is the human-facing display text.
    """

    value: str
    label: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if len(value) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(value):
            raise InvalidAttributeChoiceError(f"value {self.value!r}")
        label = self.label.strip()
        if not label or len(label) > _LABEL_MAX_LENGTH:
            raise InvalidAttributeChoiceError(f"label {self.label!r}")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "label", label)
