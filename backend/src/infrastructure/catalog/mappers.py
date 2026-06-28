"""Mapping between the Attribute domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.catalog.entities import Attribute, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode, ProductTypeCode
from src.infrastructure.catalog.models import AttributeModel, ProductTypeModel


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


def product_type_to_domain(model: ProductTypeModel) -> ProductType:
    """Rebuild a product type from a persisted row and its ordered attribute links.

    Relies on the caller having loaded ``attribute_links`` (and each link's
    ``attribute``), ordered by position via the link model's ``Meta.ordering``.
    """
    return ProductType(
        id=model.pk,
        code=ProductTypeCode(model.code),
        name=model.name,
        attributes=tuple(
            AttributeCode(link.attribute.code) for link in model.attribute_links.all()
        ),
    )


def apply_product_type_scalar_fields(
    product_type: ProductType, model: ProductTypeModel
) -> ProductTypeModel:
    """Copy the product type's own (non-attribute) fields onto an ORM instance."""
    model.code = product_type.code.value
    model.name = product_type.name
    return model
