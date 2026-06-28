"""Django ORM models for catalog persistence.

Infrastructure detail, intentionally separate from the domain entities. The
repository maps between the two so the domain never depends on the ORM. An
attribute's choices live in a child table (one row per option) rather than an
opaque blob, so they stay queryable and individually constrained.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from src.domain.catalog.enums import AttributeInputType

_CODE_MAX_LENGTH = 64
_NAME_MAX_LENGTH = 255
_INPUT_TYPE_MAX_LENGTH = 32


class AttributeModel(models.Model):
    """Storage representation of a dynamic attribute definition."""

    _INPUT_TYPE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        (input_type.value, input_type.value) for input_type in AttributeInputType
    ]

    code = models.SlugField(max_length=_CODE_MAX_LENGTH, unique=True)
    name = models.CharField(max_length=_NAME_MAX_LENGTH)
    input_type = models.CharField(max_length=_INPUT_TYPE_MAX_LENGTH, choices=_INPUT_TYPE_CHOICES)
    required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "catalog"
        db_table = "catalog_attribute"
        ordering = ("code",)
        verbose_name = "attribute"
        verbose_name_plural = "attributes"
        # Global RBAC permission gating every catalog-schema mutation. The
        # codename mirrors src.domain.catalog.permissions.MANAGE_CATALOG.
        permissions: ClassVar[list[tuple[str, str]]] = [  # type: ignore[assignment]
            ("manage_catalog", "Can manage the catalog (attributes, product types, products)"),
        ]

    def __str__(self) -> str:
        return self.code


class AttributeChoiceModel(models.Model):
    """One allowed option of a choice-type attribute."""

    attribute = models.ForeignKey(
        AttributeModel, related_name="choices", on_delete=models.CASCADE
    )
    value = models.SlugField(max_length=_CODE_MAX_LENGTH)
    label = models.CharField(max_length=_NAME_MAX_LENGTH)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "catalog"
        db_table = "catalog_attribute_choice"
        ordering = ("position",)
        # A choice value is the stable key within its attribute; it must be unique
        # there so a product can reference it unambiguously.
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["attribute", "value"], name="uniq_choice_value_per_attribute"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attribute_id}:{self.value}"


class ProductTypeModel(models.Model):
    """Storage representation of a product type (a named attribute template)."""

    code = models.SlugField(max_length=_CODE_MAX_LENGTH, unique=True)
    name = models.CharField(max_length=_NAME_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Attributes are reached through the ordered ``attribute_links`` relation
    # (the ProductTypeAttributeModel through table); no plain M2M descriptor is
    # exposed since every read must respect the assignment order.

    class Meta:
        app_label = "catalog"
        db_table = "catalog_product_type"
        ordering = ("code",)
        verbose_name = "product type"
        verbose_name_plural = "product types"

    def __str__(self) -> str:
        return self.code


class ProductTypeAttributeModel(models.Model):
    """Ordered assignment of an attribute to a product type (M2M through row)."""

    product_type = models.ForeignKey(
        ProductTypeModel, related_name="attribute_links", on_delete=models.CASCADE
    )
    attribute = models.ForeignKey(
        AttributeModel, related_name="product_type_links", on_delete=models.PROTECT
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "catalog"
        db_table = "catalog_product_type_attribute"
        ordering = ("position",)
        # An attribute is assigned to a product type at most once.
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["product_type", "attribute"],
                name="uniq_attribute_per_product_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_type_id}:{self.attribute_id}"


class ProductModel(models.Model):
    """Storage representation of a product built on a product type."""

    code = models.SlugField(max_length=_CODE_MAX_LENGTH, unique=True)
    name = models.CharField(max_length=_NAME_MAX_LENGTH)
    product_type = models.ForeignKey(
        ProductTypeModel, related_name="products", on_delete=models.PROTECT
    )
    # Free-form, string-keyed extension data (JSONB in Postgres). Never used for
    # money, which is modelled with Decimal in the pricing slice.
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "catalog"
        db_table = "catalog_product"
        ordering = ("code",)
        verbose_name = "product"
        verbose_name_plural = "products"

    def __str__(self) -> str:
        return self.code


class ProductAttributeValueModel(models.Model):
    """A product's value for one of its product type's attributes."""

    product = models.ForeignKey(
        ProductModel, related_name="attribute_values", on_delete=models.CASCADE
    )
    attribute = models.ForeignKey(
        AttributeModel, related_name="product_values", on_delete=models.PROTECT
    )
    # Canonical string form of the value (text, number, boolean literal, or choice
    # slug); the domain decides conformance before it is stored here.
    value = models.TextField()
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "catalog"
        db_table = "catalog_product_attribute_value"
        ordering = ("position",)
        # A product holds at most one value per attribute.
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["product", "attribute"],
                name="uniq_value_per_product_attribute",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}:{self.attribute_id}"
