"""Mapping between the Attribute domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.catalog.entities import (
    Attribute,
    Category,
    Collection,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.value_objects import (
    AttributeChoice,
    AttributeCode,
    AttributeValue,
    CategorySlug,
    CollectionSlug,
    MediaAsset,
    ProductCode,
    ProductTypeCode,
    Sku,
)
from src.infrastructure.catalog.models import (
    VARIANT_ATTRIBUTE_KIND,
    AttributeModel,
    CategoryModel,
    CollectionModel,
    ProductModel,
    ProductTypeModel,
    ProductVariantModel,
)


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
    ``attribute``), ordered by (kind, position) via the link model's
    ``Meta.ordering`` so each level comes back in its declared order.
    """
    product_attributes: list[AttributeCode] = []
    variant_attributes: list[AttributeCode] = []
    for link in model.attribute_links.all():
        code = AttributeCode(link.attribute.code)
        bucket = variant_attributes if link.kind == VARIANT_ATTRIBUTE_KIND else product_attributes
        bucket.append(code)
    return ProductType(
        id=model.pk,
        code=ProductTypeCode(model.code),
        name=model.name,
        attributes=tuple(product_attributes),
        variant_attributes=tuple(variant_attributes),
    )


def apply_product_type_scalar_fields(
    product_type: ProductType, model: ProductTypeModel
) -> ProductTypeModel:
    """Copy the product type's own (non-attribute) fields onto an ORM instance."""
    model.code = product_type.code.value
    model.name = product_type.name
    return model


def product_to_domain(model: ProductModel) -> Product:
    """Rebuild a product from a persisted row and its ordered attribute values.

    Relies on the caller having loaded ``attribute_values`` (and each value's
    ``attribute``), ordered by position via the value model's ``Meta.ordering``.
    """
    return Product(
        id=model.pk,
        code=ProductCode(model.code),
        name=model.name,
        product_type=ProductTypeCode(model.product_type.code),
        values=tuple(
            AttributeValue(attribute=AttributeCode(value.attribute.code), value=value.value)
            for value in model.attribute_values.all()
        ),
        metadata=dict(model.metadata),
        is_published=model.is_published,
    )


def apply_product_scalar_fields(product: Product, model: ProductModel) -> ProductModel:
    """Copy the product's own (non-relational) fields onto an ORM instance.

    The ``product_type`` foreign key is set by the repository, which resolves the
    referenced code to a row.
    """
    model.code = product.code.value
    model.name = product.name
    model.metadata = dict(product.metadata)
    model.is_published = product.is_published
    return model


def variant_to_domain(model: ProductVariantModel) -> ProductVariant:
    """Rebuild a variant from a persisted row and its ordered option values.

    Relies on the caller having loaded the related ``product`` (via
    ``select_related``) and the ``attribute_values`` (and each value's
    ``attribute``) and ``media`` (via ``prefetch_related``) so the mapper triggers
    no extra query.
    """
    return ProductVariant(
        id=model.pk,
        product=ProductCode(model.product.code),
        sku=Sku(model.sku),
        name=model.name,
        weight_grams=model.weight_grams,
        values=tuple(
            AttributeValue(attribute=AttributeCode(value.attribute.code), value=value.value)
            for value in model.attribute_values.all()
        ),
        media=tuple(
            MediaAsset(url=asset.url, alt_text=asset.alt_text) for asset in model.media.all()
        ),
    )


def apply_variant_scalar_fields(
    variant: ProductVariant, model: ProductVariantModel
) -> ProductVariantModel:
    """Copy the variant's own (non-relational) fields onto an ORM instance.

    The ``product`` foreign key is set by the repository, which resolves the
    referenced code to a row.
    """
    model.sku = variant.sku.value
    model.name = variant.name
    model.weight_grams = variant.weight_grams
    return model


def category_to_domain(model: CategoryModel) -> Category:
    """Rebuild a category from a persisted row and its optional parent link.

    Relies on the caller having loaded the related ``parent`` (via
    ``select_related``) so the mapper triggers no extra query when reading the
    parent slug.
    """
    parent = model.parent
    return Category(
        id=model.pk,
        slug=CategorySlug(model.slug),
        name=model.name,
        parent=CategorySlug(parent.slug) if parent is not None else None,
    )


def apply_category_scalar_fields(category: Category, model: CategoryModel) -> CategoryModel:
    """Copy the category's own (non-relational) fields onto an ORM instance.

    The ``parent`` foreign key is set by the repository, which resolves the
    referenced slug to a row.
    """
    model.slug = category.slug.value
    model.name = category.name
    return model


def collection_to_domain(model: CollectionModel) -> Collection:
    """Rebuild a collection from a persisted row."""
    return Collection(id=model.pk, slug=CollectionSlug(model.slug), name=model.name)


def apply_collection_scalar_fields(
    collection: Collection, model: CollectionModel
) -> CollectionModel:
    """Copy the collection's own fields onto an ORM instance."""
    model.slug = collection.slug.value
    model.name = collection.name
    return model
