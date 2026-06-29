"""Domain services for the catalog context (pure Python, no framework).

A domain service holds business logic that spans more than one entity (or a whole
collection) and so belongs to none of them. Two live here:

- *attribute-value conformance*: a product's values must match the attributes its
  product type assigns -- a rule that needs both the product's values and the
  attribute definitions, which no single entity owns.
- *category-assignment uniqueness*: a product references a category at most once.
- *collection-membership uniqueness*: a collection lists a product at most once.

The application layer fetches the data and calls these services; the rules
themselves stay in the domain.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation

from src.domain.catalog.entities import Attribute
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    DuplicateCategoryAssignmentError,
    DuplicateProductMembershipError,
    InvalidAttributeValueError,
    MissingRequiredAttributeError,
    UnassignedAttributeError,
)
from src.domain.catalog.value_objects import AttributeValue, CategorySlug, ProductCode

# Accepted boolean literals; values are normalized to these canonical forms.
_TRUE = "true"
_FALSE = "false"
_BOOLEAN_LITERALS = frozenset({_TRUE, _FALSE})


def normalize_attribute_values(
    attributes: Sequence[Attribute],
    values: Sequence[AttributeValue],
) -> tuple[AttributeValue, ...]:
    """Validate values against a product type's attributes and canonicalize them.

    ``attributes`` are the product type's attribute definitions in declared order.
    Returns the values in that same order, each normalized to its canonical string
    form (a number parsed as ``Decimal``, a lower-case boolean literal, a choice
    slug, or trimmed text). Raises a catalog domain error if a value references an
    unassigned attribute, a required attribute has no value, or a value does not
    conform to its attribute's input type.
    """
    definitions = {attribute.code.value: attribute for attribute in attributes}
    provided = _index_provided_values(definitions, values)

    normalized: list[AttributeValue] = []
    for attribute in attributes:
        code = attribute.code.value
        raw = provided.get(code)
        if raw is None:
            if attribute.required:
                raise MissingRequiredAttributeError(code)
            continue
        normalized.append(
            AttributeValue(attribute=attribute.code, value=_normalize_one(attribute, raw))
        )
    return tuple(normalized)


def _index_provided_values(
    definitions: dict[str, Attribute], values: Sequence[AttributeValue]
) -> dict[str, str]:
    """Map each provided value to its attribute code, rejecting unassigned ones."""
    provided: dict[str, str] = {}
    for value in values:
        code = value.attribute.value
        if code not in definitions:
            raise UnassignedAttributeError(code)
        provided[code] = value.value
    return provided


def _normalize_text(attribute: Attribute, raw: str) -> str:
    text = raw.strip()
    if not text:
        raise InvalidAttributeValueError(attribute.code.value, "text must not be blank")
    return text


def _normalize_number(attribute: Attribute, raw: str) -> str:
    try:
        number = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise InvalidAttributeValueError(attribute.code.value, f"not a number: {raw!r}") from exc
    if not number.is_finite():
        raise InvalidAttributeValueError(attribute.code.value, f"not a finite number: {raw!r}")
    return str(number)


def _normalize_boolean(attribute: Attribute, raw: str) -> str:
    literal = raw.strip().lower()
    if literal not in _BOOLEAN_LITERALS:
        raise InvalidAttributeValueError(attribute.code.value, f"not a boolean: {raw!r}")
    return literal


def _normalize_choice(attribute: Attribute, raw: str) -> str:
    choice = raw.strip()
    allowed = {option.value for option in attribute.choices}
    if choice not in allowed:
        raise InvalidAttributeValueError(attribute.code.value, f"not an allowed choice: {raw!r}")
    return choice


# Scalar (non-choice) input types map directly to a normalizer; the choice type
# needs the attribute's declared options, so it is handled separately.
_SCALAR_NORMALIZERS: dict[AttributeInputType, Callable[[Attribute, str], str]] = {
    AttributeInputType.PLAIN_TEXT: _normalize_text,
    AttributeInputType.NUMBER: _normalize_number,
    AttributeInputType.BOOLEAN: _normalize_boolean,
}


def _normalize_one(attribute: Attribute, raw: str) -> str:
    if attribute.input_type.is_choice_type:
        return _normalize_choice(attribute, raw)
    return _SCALAR_NORMALIZERS[attribute.input_type](attribute, raw)


def reject_duplicate_categories(
    categories: Sequence[CategorySlug],
) -> tuple[CategorySlug, ...]:
    """Return the assignment unchanged, rejecting a category listed twice.

    A product belongs to a category at most once; a repeated slug is a malformed
    assignment, not a silently-collapsed set, so it is surfaced as a domain error.
    """
    seen: set[str] = set()
    for category in categories:
        if category.value in seen:
            raise DuplicateCategoryAssignmentError(category.value)
        seen.add(category.value)
    return tuple(categories)


def reject_duplicate_products(
    products: Sequence[ProductCode],
) -> tuple[ProductCode, ...]:
    """Return the membership unchanged, rejecting a product listed twice.

    A collection lists a product at most once; a repeated code is a malformed
    membership, not a silently-collapsed set, so it is surfaced as a domain error.
    """
    seen: set[str] = set()
    for product in products:
        if product.value in seen:
            raise DuplicateProductMembershipError(product.value)
        seen.add(product.value)
    return tuple(products)
