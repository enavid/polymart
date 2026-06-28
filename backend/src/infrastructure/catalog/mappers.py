"""Mapping between the Attribute domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.catalog.entities import Attribute
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode
from src.infrastructure.catalog.models import AttributeModel


def to_domain(model: AttributeModel) -> Attribute:
    """Rebuild a domain entity from a persisted row and its choice rows.

    Relies on the caller having loaded ``choices`` (ordered by position via the
    child model's ``Meta.ordering``).
    """
    return Attribute(
        id=model.pk,
        code=AttributeCode(model.code),
        name=model.name,
        input_type=AttributeInputType(model.input_type),
        required=model.required,
        choices=tuple(
            AttributeChoice(value=choice.value, label=choice.label)
            for choice in model.choices.all()
        ),
    )


def apply_scalar_fields(attribute: Attribute, model: AttributeModel) -> AttributeModel:
    """Copy the attribute's own (non-choice) fields onto an ORM instance."""
    model.code = attribute.code.value
    model.name = attribute.name
    model.input_type = attribute.input_type.value
    model.required = attribute.required
    return model
