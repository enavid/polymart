"""Composition root for the catalog slice.

The only place that wires concrete infrastructure adapters into the use cases.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.catalog.use_cases import (
    AdjustVariantStock,
    CreateAttribute,
    CreateCategory,
    CreateCollection,
    CreateProduct,
    CreateProductType,
    CreateVariant,
    ExportCatalogProducts,
    GetAttribute,
    GetCategory,
    GetCollection,
    GetCollectionProducts,
    GetCollectionRule,
    GetCollectionRuleMembers,
    GetProduct,
    GetProductCategories,
    GetProductType,
    GetPublishedProduct,
    GetStorefrontProductVariants,
    GetVariant,
    GetVariantPrices,
    GetVariantStock,
    ImportCatalogProducts,
    ListAttributes,
    ListCategories,
    ListCollections,
    ListProducts,
    ListProductTypes,
    ListProductVariants,
    SearchCatalogProducts,
    SetCollectionProducts,
    SetCollectionRule,
    SetProductCategories,
    SetProductPublished,
    SetVariantPrices,
    SetVariantStock,
)
from src.infrastructure.catalog.repositories import (
    DjangoAttributeRepository,
    DjangoCatalogImportWriter,
    DjangoCategoryRepository,
    DjangoChannelReader,
    DjangoCollectionProductRepository,
    DjangoCollectionRepository,
    DjangoCollectionRuleRepository,
    DjangoProductCategoryRepository,
    DjangoProductQueryRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantPriceRepository,
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


def build_create_collection() -> CreateCollection:
    return CreateCollection(DjangoCollectionRepository(), build_audit_recorder())


def build_get_collection() -> GetCollection:
    return GetCollection(DjangoCollectionRepository())


def build_list_collections() -> ListCollections:
    return ListCollections(DjangoCollectionRepository())


def build_set_collection_products() -> SetCollectionProducts:
    return SetCollectionProducts(
        DjangoCollectionProductRepository(),
        DjangoCollectionRepository(),
        DjangoProductRepository(),
        build_audit_recorder(),
    )


def build_get_collection_products() -> GetCollectionProducts:
    return GetCollectionProducts(DjangoCollectionProductRepository(), DjangoCollectionRepository())


def build_set_collection_rule() -> SetCollectionRule:
    return SetCollectionRule(
        DjangoCollectionRuleRepository(),
        DjangoCollectionRepository(),
        DjangoAttributeRepository(),
        build_audit_recorder(),
    )


def build_get_collection_rule() -> GetCollectionRule:
    return GetCollectionRule(DjangoCollectionRuleRepository(), DjangoCollectionRepository())


def build_get_collection_rule_members() -> GetCollectionRuleMembers:
    return GetCollectionRuleMembers(
        DjangoCollectionRuleRepository(),
        DjangoCollectionRepository(),
        DjangoProductRepository(),
    )


def build_set_variant_prices() -> SetVariantPrices:
    return SetVariantPrices(
        DjangoVariantPriceRepository(),
        DjangoVariantRepository(),
        DjangoChannelReader(),
        build_audit_recorder(),
    )


def build_get_variant_prices() -> GetVariantPrices:
    return GetVariantPrices(DjangoVariantPriceRepository(), DjangoVariantRepository())


def build_set_variant_stock() -> SetVariantStock:
    return SetVariantStock(
        DjangoStockRepository(), DjangoVariantRepository(), build_audit_recorder()
    )


def build_adjust_variant_stock() -> AdjustVariantStock:
    return AdjustVariantStock(
        DjangoStockRepository(), DjangoVariantRepository(), build_audit_recorder()
    )


def build_get_variant_stock() -> GetVariantStock:
    return GetVariantStock(DjangoStockRepository(), DjangoVariantRepository())


def build_set_product_published() -> SetProductPublished:
    return SetProductPublished(DjangoProductRepository(), build_audit_recorder())


def build_search_catalog_products() -> SearchCatalogProducts:
    return SearchCatalogProducts(DjangoProductQueryRepository())


def build_get_published_product() -> GetPublishedProduct:
    return GetPublishedProduct(DjangoProductQueryRepository())


def build_get_storefront_product_variants() -> GetStorefrontProductVariants:
    return GetStorefrontProductVariants(
        DjangoProductQueryRepository(),
        DjangoVariantRepository(),
        DjangoVariantPriceRepository(),
    )


def build_export_catalog_products() -> ExportCatalogProducts:
    return ExportCatalogProducts(DjangoProductRepository(), DjangoProductCategoryRepository())


def build_import_catalog_products() -> ImportCatalogProducts:
    return ImportCatalogProducts(
        DjangoProductRepository(),
        DjangoProductTypeRepository(),
        DjangoAttributeRepository(),
        DjangoCategoryRepository(),
        DjangoCatalogImportWriter(),
        build_audit_recorder(),
    )
