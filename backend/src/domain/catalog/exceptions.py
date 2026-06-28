"""Domain exceptions for the catalog context.

Pure-Python exceptions with no framework coupling. The interface layer translates
them into transport-level responses (HTTP codes).
"""

from __future__ import annotations


class CatalogError(Exception):
    """Base class for every catalog domain error."""


class InvalidAttributeCodeError(CatalogError):
    """Raised when an attribute code is empty, too long, or not a slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid attribute code: {value!r}")
        self.value = value


class InvalidAttributeNameError(CatalogError):
    """Raised when an attribute display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid attribute name: {value!r}")
        self.value = value


class InvalidAttributeInputTypeError(CatalogError):
    """Raised when a raw input-type string matches no known attribute type."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid attribute input type: {value!r}")
        self.value = value


class InvalidAttributeChoiceError(CatalogError):
    """Raised when a choice's value or label is malformed."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid attribute choice: {detail}")
        self.detail = detail


class AttributeChoicesRequiredError(CatalogError):
    """Raised when a choice-type attribute is created without any choices."""

    def __init__(self, input_type: str) -> None:
        super().__init__(f"input type {input_type!r} requires at least one choice")
        self.input_type = input_type


class AttributeChoicesNotAllowedError(CatalogError):
    """Raised when a non-choice attribute is given choices it cannot use."""

    def __init__(self, input_type: str) -> None:
        super().__init__(f"input type {input_type!r} does not accept choices")
        self.input_type = input_type


class DuplicateAttributeChoiceError(CatalogError):
    """Raised when two choices share the same value within one attribute."""

    def __init__(self, value: str) -> None:
        super().__init__(f"duplicate attribute choice value: {value!r}")
        self.value = value


class AttributeNotFoundError(CatalogError):
    """Raised when an attribute cannot be located by its code."""

    def __init__(self, code: str) -> None:
        super().__init__(f"attribute not found: {code!r}")
        self.code = code


class AttributeAlreadyExistsError(CatalogError):
    """Raised when creating an attribute whose code is already taken."""

    def __init__(self, code: str) -> None:
        super().__init__(f"attribute already exists: {code!r}")
        self.code = code
