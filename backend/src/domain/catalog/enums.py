"""Enumerations for the catalog context (pure domain)."""

from __future__ import annotations

from enum import Enum


class AttributeInputType(Enum):
    """How a dynamic attribute captures its value.

    Choice types (currently only ``DROPDOWN``) draw their value from a fixed,
    pre-declared set; every other type captures a free-form value. The
    ``is_choice_type`` flag is the single source of that distinction so the
    entity's choice rules never enumerate the membership inline.
    """

    PLAIN_TEXT = "plain_text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DROPDOWN = "dropdown"

    @property
    def is_choice_type(self) -> bool:
        """Whether this type draws its value from a declared set of choices."""
        return self in _CHOICE_TYPES


# Defined after the class so the membership set can reference its members.
_CHOICE_TYPES = frozenset({AttributeInputType.DROPDOWN})


class RuleOperator(Enum):
    """How a rule-based collection condition compares a product's attribute value.

    A rule selects products whose attribute values satisfy a conjunction of such
    conditions. Comparison is on the canonical, normalized string the catalog
    already stores for each value, so equality is exact for every input type.
    Ordered/range operators (greater-than, ...) are a deliberate follow-up.
    """

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
