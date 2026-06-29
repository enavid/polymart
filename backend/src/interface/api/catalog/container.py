"""Composition root for the catalog slice.

The only place that wires concrete infrastructure adapters into the use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.catalog.use_cases import (
    CreateAttribute,
    CreateCategory,
    CreateProduct,
    CreateProductType,
    CreateVariant,
    GetAttribute,
    GetCategory,
    GetProduct,
    GetProductCategories,
    GetProductType,
    GetVariant,
    ListAttributes,
    ListCategories,
    ListProducts,
    ListProductTypes,
    ListProductVariants,
    SetProductCategories,
)
from src.infrastructure.catalog.repositories import (
    DjangoAttributeRepository,
    DjangoCategoryRepository,
    DjangoProductCategoryRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoVariantRepository,
)
from src.interface.api.audit.container import build_audit_recorder


def build_create_attribute() -> CreateAttribute:
    return CreateAttribute(DjangoAttributeRepository(), build_audit_recorder())


def build_get_attribute() -> GetAttribute:
    return GetAttribute(DjangoAttributeRepository())


def build_list_attributes() -> ListAttributes:
    return ListAttributes(DjangoAttributeRepository())


def build_create_product_type() -> CreateProductType:
    return CreateProductType(
        DjangoProductTypeRepository(), DjangoAttributeRepository(), build_audit_recorder()
    )


def build_get_product_type() -> GetProductType:
    return GetProductType(DjangoProductTypeRepository())


def build_list_product_types() -> ListProductTypes:
    return ListProductTypes(DjangoProductTypeRepository())


def build_create_product() -> CreateProduct:
    return CreateProduct(
        DjangoProductRepository(),
        DjangoProductTypeRepository(),
        DjangoAttributeRepository(),
        build_audit_recorder(),
    )


def build_get_product() -> GetProduct:
    return GetProduct(DjangoProductRepository())


def build_list_products() -> ListProducts:
    return ListProducts(DjangoProductRepository())


def build_create_variant() -> CreateVariant:
    return CreateVariant(
        DjangoVariantRepository(),
        DjangoProductRepository(),
        DjangoProductTypeRepository(),
        DjangoAttributeRepository(),
        build_audit_recorder(),
    )


def build_get_variant() -> GetVariant:
    return GetVariant(DjangoVariantRepository())


def build_list_product_variants() -> ListProductVariants:
    return ListProductVariants(DjangoVariantRepository(), DjangoProductRepository())


def build_create_category() -> CreateCategory:
    return CreateCategory(DjangoCategoryRepository(), build_audit_recorder())


def build_get_category() -> GetCategory:
    return GetCategory(DjangoCategoryRepository())


def build_list_categories() -> ListCategories:
    return ListCategories(DjangoCategoryRepository())


def build_set_product_categories() -> SetProductCategories:
    return SetProductCategories(
        DjangoProductCategoryRepository(),
        DjangoProductRepository(),
        DjangoCategoryRepository(),
        build_audit_recorder(),
    )


def build_get_product_categories() -> GetProductCategories:
    return GetProductCategories(DjangoProductCategoryRepository(), DjangoProductRepository())
