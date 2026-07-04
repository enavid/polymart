"""Catalog endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result. They hold no
business logic. Domain exceptions are translated to HTTP status codes here -- the
one place where the domain meets the transport.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.catalog.ports import PriceSummary, ProductPage
from src.application.catalog.use_cases import (
    AdjustVariantStockCommand,
    AttributeChoiceInput,
    AttributeValueInput,
    ChannelPriceInput,
    CreateAttributeCommand,
    CreateCategoryCommand,
    CreateCollectionCommand,
    CreateProductCommand,
    CreateProductTypeCommand,
    CreateVariantCommand,
    MediaInput,
    ProductImportResult,
    RuleConditionInput,
    SearchCatalogProductsQuery,
    SetCollectionProductsCommand,
    SetCollectionRuleCommand,
    SetProductCategoriesCommand,
    SetProductPublishedCommand,
    SetVariantPricesCommand,
    SetVariantStockCommand,
    StorefrontVariant,
)
from src.domain.catalog.entities import (
    Attribute,
    Category,
    Collection,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
    CatalogError,
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import (
    CategorySlug,
    ChannelPrice,
    MediaAsset,
    ProductCode,
    RuleCondition,
    StockQuantity,
)
from src.interface.api.access.permissions import CatalogManagePermission
from src.interface.api.catalog.container import (
    build_adjust_variant_stock,
    build_create_attribute,
    build_create_category,
    build_create_collection,
    build_create_product,
    build_create_product_type,
    build_create_variant,
    build_export_catalog_products,
    build_get_attribute,
    build_get_category,
    build_get_collection,
    build_get_collection_products,
    build_get_collection_rule,
    build_get_collection_rule_members,
    build_get_product,
    build_get_product_categories,
    build_get_product_type,
    build_get_published_product,
    build_get_storefront_product_images,
    build_get_storefront_product_variants,
    build_get_variant,
    build_get_variant_prices,
    build_get_variant_stock,
    build_import_catalog_products,
    build_list_attributes,
    build_list_categories,
    build_list_collections,
    build_list_product_types,
    build_list_product_variants,
    build_list_products,
    build_search_catalog_products,
    build_set_collection_products,
    build_set_collection_rule,
    build_set_product_categories,
    build_set_product_published,
    build_set_variant_prices,
    build_set_variant_stock,
    build_summarise_storefront_prices,
)
from src.interface.api.catalog.csv_io import CsvFormatError, decode_products, encode_products
from src.interface.api.catalog.serializers import (
    AdjustVariantStockSerializer,
    AttributeSerializer,
    CategorySerializer,
    CollectionProductsSerializer,
    CollectionRuleMembersSerializer,
    CollectionRuleSerializer,
    CollectionSerializer,
    CreateAttributeSerializer,
    CreateCategorySerializer,
    CreateCollectionSerializer,
    CreateProductSerializer,
    CreateProductTypeSerializer,
    CreateVariantSerializer,
    ProductCategoriesSerializer,
    ProductImportRequestSerializer,
    ProductImportResultSerializer,
    ProductSerializer,
    ProductTypeSerializer,
    SetProductPublishedSerializer,
    SetVariantPricesSerializer,
    SetVariantStockSerializer,
    StorefrontCategorySerializer,
    StorefrontCollectionSerializer,
    StorefrontProductPageSerializer,
    StorefrontProductQuerySerializer,
    StorefrontProductSerializer,
    StorefrontProductTypeSerializer,
    StorefrontProductVariantsSerializer,
    StorefrontVariantsQuerySerializer,
    VariantPricesSerializer,
    VariantSerializer,
    VariantStockSerializer,
)
from src.interface.api.common import ErrorSerializer

# A bulk import is loaded into memory before parsing, so its byte size is capped at
# the edge (the row count is capped separately by the use case) to bound the upload.
_MAX_IMPORT_BYTES = 5 * 1024 * 1024

logger = structlog.get_logger(__name__)


def _actor(request: Request) -> str | None:
    """Identify the authenticated user behind a mutation for the audit trail.

    Uses the stable primary key, not the username: the username is the phone
    number (PII), which must never reach the logs.
    """
    user = request.user
    return str(user.pk) if user.is_authenticated else None


def _payload(attribute: Attribute) -> dict[str, object]:
    """Project a domain entity to the response body.

    This is the single source of the response shape; ``AttributeSerializer`` exists
    only to document that shape in the OpenAPI schema (the domain entity, with its
    value objects, cannot be fed to a serializer directly).
    """
    return {
        "id": attribute.id,
        "code": attribute.code.value,
        "name": attribute.name,
        "input_type": attribute.input_type.value,
        "required": attribute.required,
        "choices": [{"value": choice.value, "label": choice.label} for choice in attribute.choices],
    }


class AttributeListCreateView(APIView):
    """List attribute definitions or create a new one."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses=AttributeSerializer(many=True))
    def get(self, request: Request) -> Response:
        attributes = build_list_attributes().execute()
        return Response([_payload(attribute) for attribute in attributes])

    @extend_schema(
        request=CreateAttributeSerializer,
        responses={
            201: AttributeSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateAttributeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateAttributeCommand(
            code=data["code"],
            name=data["name"],
            input_type=data["input_type"],
            required=data["required"],
            choices=tuple(
                AttributeChoiceInput(value=choice["value"], label=choice["label"])
                for choice in data["choices"]
            ),
        )
        try:
            attribute = build_create_attribute().execute(command, actor=_actor(request))
        except AttributeAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CatalogError as exc:
            # Invalid code/name/input-type/choices surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_payload(attribute), status=status.HTTP_201_CREATED)


class AttributeDetailView(APIView):
    """Retrieve a single attribute by code."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: AttributeSerializer, 404: ErrorSerializer})
    def get(self, request: Request, code: str) -> Response:
        try:
            attribute = build_get_attribute().execute(code=code)
        except AttributeNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_payload(attribute))


def _product_type_payload(product_type: ProductType) -> dict[str, object]:
    """Project a product-type entity to the response body."""
    return {
        "id": product_type.id,
        "code": product_type.code.value,
        "name": product_type.name,
        "attributes": [attribute.value for attribute in product_type.attributes],
        "variant_attributes": [attribute.value for attribute in product_type.variant_attributes],
    }


class ProductTypeListCreateView(APIView):
    """List product types or create a new one."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses=ProductTypeSerializer(many=True))
    def get(self, request: Request) -> Response:
        product_types = build_list_product_types().execute()
        return Response([_product_type_payload(pt) for pt in product_types])

    @extend_schema(
        request=CreateProductTypeSerializer,
        responses={
            201: ProductTypeSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateProductTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateProductTypeCommand(
            code=data["code"],
            name=data["name"],
            attributes=tuple(data["attributes"]),
            variant_attributes=tuple(data["variant_attributes"]),
        )
        try:
            product_type = build_create_product_type().execute(command, actor=_actor(request))
        except ProductTypeAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CatalogError as exc:
            # Invalid code/name, duplicate or unknown attribute reference.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_product_type_payload(product_type), status=status.HTTP_201_CREATED)


class ProductTypeDetailView(APIView):
    """Retrieve a single product type by code."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: ProductTypeSerializer, 404: ErrorSerializer})
    def get(self, request: Request, code: str) -> Response:
        try:
            product_type = build_get_product_type().execute(code=code)
        except ProductTypeNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_product_type_payload(product_type))


def _product_payload(product: Product) -> dict[str, object]:
    """Project a product entity to the response body."""
    return {
        "id": product.id,
        "code": product.code.value,
        "name": product.name,
        "product_type": product.product_type.value,
        "values": [
            {"attribute": value.attribute.value, "value": value.value} for value in product.values
        ],
        "metadata": dict(product.metadata),
        "is_published": product.is_published,
    }


class ProductListCreateView(APIView):
    """List products or create a new one."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses=ProductSerializer(many=True))
    def get(self, request: Request) -> Response:
        products = build_list_products().execute()
        return Response([_product_payload(product) for product in products])

    @extend_schema(
        request=CreateProductSerializer,
        responses={
            201: ProductSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateProductCommand(
            code=data["code"],
            name=data["name"],
            product_type=data["product_type"],
            values=tuple(
                AttributeValueInput(attribute=item["attribute"], value=item["value"])
                for item in data["values"]
            ),
            metadata=data["metadata"],
        )
        try:
            product = build_create_product().execute(command, actor=_actor(request))
        except ProductAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CatalogError as exc:
            # Invalid code/name/metadata, unknown product type, or a value that
            # does not conform to its attribute (missing/unassigned/malformed).
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_product_payload(product), status=status.HTTP_201_CREATED)


class ProductDetailView(APIView):
    """Retrieve a single product by code."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: ProductSerializer, 404: ErrorSerializer})
    def get(self, request: Request, code: str) -> Response:
        try:
            product = build_get_product().execute(code=code)
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_product_payload(product))


class ProductPublicationView(APIView):
    """Publish or unpublish a product (admin; controls storefront visibility)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(
        request=SetProductPublishedSerializer,
        responses={
            200: ProductSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, code: str) -> Response:
        serializer = SetProductPublishedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SetProductPublishedCommand(
            product=code, is_published=serializer.validated_data["is_published"]
        )
        try:
            product = build_set_product_published().execute(command, actor=_actor(request))
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_product_payload(product))


def _variant_payload(variant: ProductVariant) -> dict[str, object]:
    """Project a variant entity to the response body."""
    return {
        "id": variant.id,
        "product": variant.product.value,
        "sku": variant.sku.value,
        "name": variant.name,
        "values": [
            {"attribute": value.attribute.value, "value": value.value} for value in variant.values
        ],
        "media": [{"url": asset.url, "alt_text": asset.alt_text} for asset in variant.media],
    }


class ProductVariantListCreateView(APIView):
    """List the variants of a product or create a new one (nested under the product)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: VariantSerializer(many=True), 404: ErrorSerializer})
    def get(self, request: Request, code: str) -> Response:
        try:
            variants = build_list_product_variants().execute(product_code=code)
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response([_variant_payload(variant) for variant in variants])

    @extend_schema(
        request=CreateVariantSerializer,
        responses={
            201: VariantSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, code: str) -> Response:
        serializer = CreateVariantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateVariantCommand(
            product=code,
            sku=data["sku"],
            name=data["name"],
            values=tuple(
                AttributeValueInput(attribute=item["attribute"], value=item["value"])
                for item in data["values"]
            ),
            media=tuple(
                MediaInput(url=item["url"], alt_text=item["alt_text"]) for item in data["media"]
            ),
        )
        try:
            variant = build_create_variant().execute(command, actor=_actor(request))
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except VariantAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CatalogError as exc:
            # Invalid SKU or blank name surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_variant_payload(variant), status=status.HTTP_201_CREATED)


class VariantDetailView(APIView):
    """Retrieve a single variant by SKU."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: VariantSerializer, 404: ErrorSerializer})
    def get(self, request: Request, sku: str) -> Response:
        try:
            variant = build_get_variant().execute(sku=sku)
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_variant_payload(variant))


def _category_payload(category: Category) -> dict[str, object]:
    """Project a category entity to the response body (``parent`` is null for a root)."""
    return {
        "id": category.id,
        "slug": category.slug.value,
        "name": category.name,
        "parent": category.parent.value if category.parent is not None else None,
    }


class CategoryListCreateView(APIView):
    """List categories or create a new one."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses=CategorySerializer(many=True))
    def get(self, request: Request) -> Response:
        categories = build_list_categories().execute()
        return Response([_category_payload(category) for category in categories])

    @extend_schema(
        request=CreateCategorySerializer,
        responses={
            201: CategorySerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateCategoryCommand(
            slug=data["slug"],
            name=data["name"],
            parent=data["parent"],
        )
        try:
            category = build_create_category().execute(command, actor=_actor(request))
        except CategoryAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CatalogError as exc:
            # Invalid slug/name, self-parenting, or an unknown parent reference.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_category_payload(category), status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    """Retrieve a single category by slug."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: CategorySerializer, 404: ErrorSerializer})
    def get(self, request: Request, slug: str) -> Response:
        try:
            category = build_get_category().execute(slug=slug)
        except CategoryNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_category_payload(category))


def _categories_payload(categories: tuple[CategorySlug, ...]) -> dict[str, object]:
    """Project a product's category membership to the response body."""
    return {"categories": [category.value for category in categories]}


class ProductCategoriesView(APIView):
    """List or replace a product's category membership (nested under the product)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: ProductCategoriesSerializer, 404: ErrorSerializer})
    def get(self, request: Request, code: str) -> Response:
        try:
            categories = build_get_product_categories().execute(product_code=code)
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_categories_payload(categories))

    @extend_schema(
        request=ProductCategoriesSerializer,
        responses={
            200: ProductCategoriesSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, code: str) -> Response:
        serializer = ProductCategoriesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SetProductCategoriesCommand(
            product=code,
            categories=tuple(serializer.validated_data["categories"]),
        )
        try:
            categories = build_set_product_categories().execute(command, actor=_actor(request))
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CatalogError as exc:
            # A malformed/duplicate slug, or a referenced category that does not exist.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_categories_payload(categories))


def _collection_payload(collection: Collection) -> dict[str, object]:
    """Project a collection entity to the response body."""
    return {
        "id": collection.id,
        "slug": collection.slug.value,
        "name": collection.name,
    }


class CollectionListCreateView(APIView):
    """List collections or create a new one."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses=CollectionSerializer(many=True))
    def get(self, request: Request) -> Response:
        collections = build_list_collections().execute()
        return Response([_collection_payload(collection) for collection in collections])

    @extend_schema(
        request=CreateCollectionSerializer,
        responses={
            201: CollectionSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateCollectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = CreateCollectionCommand(slug=data["slug"], name=data["name"])
        try:
            collection = build_create_collection().execute(command, actor=_actor(request))
        except CollectionAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CatalogError as exc:
            # Invalid slug or blank name surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_collection_payload(collection), status=status.HTTP_201_CREATED)


class CollectionDetailView(APIView):
    """Retrieve a single collection by slug."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: CollectionSerializer, 404: ErrorSerializer})
    def get(self, request: Request, slug: str) -> Response:
        try:
            collection = build_get_collection().execute(slug=slug)
        except CollectionNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_collection_payload(collection))


def _collection_products_payload(products: tuple[ProductCode, ...]) -> dict[str, object]:
    """Project a collection's product membership to the response body."""
    return {"products": [product.value for product in products]}


class CollectionProductsView(APIView):
    """List or replace a collection's product membership (nested under the collection)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: CollectionProductsSerializer, 404: ErrorSerializer})
    def get(self, request: Request, slug: str) -> Response:
        try:
            products = build_get_collection_products().execute(collection_slug=slug)
        except CollectionNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_collection_products_payload(products))

    @extend_schema(
        request=CollectionProductsSerializer,
        responses={
            200: CollectionProductsSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, slug: str) -> Response:
        serializer = CollectionProductsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SetCollectionProductsCommand(
            collection=slug,
            products=tuple(serializer.validated_data["products"]),
        )
        try:
            products = build_set_collection_products().execute(command, actor=_actor(request))
        except CollectionNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CatalogError as exc:
            # A malformed/duplicate code, or a referenced product that does not exist.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_collection_products_payload(products))


def _collection_rule_payload(conditions: tuple[RuleCondition, ...]) -> dict[str, object]:
    """Project a collection's membership rule to the response body."""
    return {
        "conditions": [
            {
                "attribute": condition.attribute.value,
                "operator": condition.operator.value,
                "value": condition.value,
            }
            for condition in conditions
        ]
    }


class CollectionRuleView(APIView):
    """List or replace a rule-based collection's membership rule (nested under it)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: CollectionRuleSerializer, 404: ErrorSerializer})
    def get(self, request: Request, slug: str) -> Response:
        try:
            conditions = build_get_collection_rule().execute(collection_slug=slug)
        except CollectionNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_collection_rule_payload(conditions))

    @extend_schema(
        request=CollectionRuleSerializer,
        responses={
            200: CollectionRuleSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, slug: str) -> Response:
        serializer = CollectionRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SetCollectionRuleCommand(
            collection=slug,
            conditions=tuple(
                RuleConditionInput(
                    attribute=item["attribute"],
                    operator=item["operator"],
                    value=item["value"],
                )
                for item in serializer.validated_data["conditions"]
            ),
        )
        try:
            conditions = build_set_collection_rule().execute(command, actor=_actor(request))
        except CollectionNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CatalogError as exc:
            # A malformed/duplicate condition, an unknown operator, or a referenced
            # attribute that does not exist.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_collection_rule_payload(conditions))


class CollectionRuleMembersView(APIView):
    """Resolve the products a rule-based collection currently selects (read-only)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: CollectionRuleMembersSerializer, 404: ErrorSerializer})
    def get(self, request: Request, slug: str) -> Response:
        try:
            products = build_get_collection_rule_members().execute(collection_slug=slug)
        except CollectionNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_collection_products_payload(products))


def _variant_prices_payload(prices: tuple[ChannelPrice, ...]) -> dict[str, object]:
    """Project a variant's per-channel prices to the response body.

    The amount is rendered as a string so the exact Decimal survives JSON (a float
    would reintroduce the rounding error Decimal exists to avoid); the currency is
    the one derived from each channel.
    """
    return {
        "prices": [
            {
                "channel": price.channel,
                "amount": str(price.money.amount),
                "currency": price.money.currency,
            }
            for price in prices
        ]
    }


class VariantPricesView(APIView):
    """List or replace a variant's per-channel base prices (nested under the variant)."""

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: VariantPricesSerializer, 404: ErrorSerializer})
    def get(self, request: Request, sku: str) -> Response:
        try:
            prices = build_get_variant_prices().execute(sku=sku)
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_variant_prices_payload(prices))

    @extend_schema(
        request=SetVariantPricesSerializer,
        responses={
            200: VariantPricesSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, sku: str) -> Response:
        serializer = SetVariantPricesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SetVariantPricesCommand(
            variant=sku,
            prices=tuple(
                ChannelPriceInput(channel=item["channel"], amount=item["amount"])
                for item in serializer.validated_data["prices"]
            ),
        )
        try:
            prices = build_set_variant_prices().execute(command, actor=_actor(request))
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CatalogError as exc:
            # A malformed/zero/negative amount, an unknown channel, or a duplicate
            # channel price surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_variant_prices_payload(prices))


def _variant_stock_payload(quantity: StockQuantity) -> dict[str, object]:
    """Project a variant's on-hand stock quantity to the response body."""
    return {"quantity": quantity.value}


class VariantStockView(APIView):
    """Read, set, or adjust a variant's on-hand stock (nested under the variant).

    ``PUT`` sets an absolute quantity (idempotent); ``PATCH`` applies a signed delta
    atomically (an oversell is rejected, never clamped).
    """

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(responses={200: VariantStockSerializer, 404: ErrorSerializer})
    def get(self, request: Request, sku: str) -> Response:
        try:
            quantity = build_get_variant_stock().execute(sku=sku)
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(_variant_stock_payload(quantity))

    @extend_schema(
        request=SetVariantStockSerializer,
        responses={
            200: VariantStockSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, sku: str) -> Response:
        serializer = SetVariantStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = SetVariantStockCommand(
            variant=sku, quantity=serializer.validated_data["quantity"]
        )
        try:
            quantity = build_set_variant_stock().execute(command, actor=_actor(request))
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CatalogError as exc:
            # A negative or out-of-range quantity surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_variant_stock_payload(quantity))

    @extend_schema(
        request=AdjustVariantStockSerializer,
        responses={
            200: VariantStockSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def patch(self, request: Request, sku: str) -> Response:
        serializer = AdjustVariantStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = AdjustVariantStockCommand(variant=sku, delta=serializer.validated_data["delta"])
        try:
            quantity = build_adjust_variant_stock().execute(command, actor=_actor(request))
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CatalogError as exc:
            # An oversell (would go below zero) or an overflow surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_variant_stock_payload(quantity))


def _storefront_product_payload(
    product: Product,
    summary: PriceSummary | None = None,
    image: MediaAsset | None = None,
) -> dict[str, object]:
    """Project a published product for the public storefront.

    Deliberately omits the internal ``id`` (the public key is the ``code``) so the
    sequential database id is never exposed to anonymous callers. When a viewing
    channel was supplied, the pricing summary (a "from" price + availability) is
    attached so the PLP can show a price and an out-of-stock flag; the amount is a
    string so the exact Decimal survives JSON. ``image`` is the product's primary
    image (promoted from a variant) or ``null`` when it has none -- the storefront
    then falls back to its monogram placeholder.
    """
    payload: dict[str, object] = {
        "code": product.code.value,
        "name": product.name,
        "product_type": product.product_type.value,
        "values": [
            {"attribute": value.attribute.value, "value": value.value} for value in product.values
        ],
        "metadata": dict(product.metadata),
        "image": None if image is None else {"url": image.url, "alt_text": image.alt_text},
    }
    if summary is not None:
        from_price = summary.from_price
        payload["from_price"] = None if from_price is None else str(from_price.amount)
        payload["currency"] = None if from_price is None else from_price.currency
        payload["available"] = summary.available
    return payload


def _storefront_page_payload(
    page: ProductPage,
    *,
    limit: int,
    offset: int,
    summaries: dict[str, PriceSummary] | None = None,
    images: dict[str, MediaAsset] | None = None,
) -> dict[str, object]:
    """Project a page of storefront products to the response body."""
    return {
        "count": page.total,
        "limit": limit,
        "offset": offset,
        "results": [
            _storefront_product_payload(
                product,
                None if summaries is None else summaries.get(product.code.value),
                None if images is None else images.get(product.code.value),
            )
            for product in page.items
        ],
    }


class StorefrontProductListView(APIView):
    """Public, paginated, filterable list of published products (the PLP source)."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="storefront_products_list",
        parameters=[StorefrontProductQuerySerializer],
        responses={200: StorefrontProductPageSerializer, 400: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        params = StorefrontProductQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        query = SearchCatalogProductsQuery(
            search=data.get("search"),
            category=data.get("category"),
            collection=data.get("collection"),
            product_type=data.get("product_type"),
            channel=data.get("channel"),
            min_price=data.get("min_price"),
            max_price=data.get("max_price"),
            **_window_kwargs(data),
        )
        try:
            page = build_search_catalog_products().execute(query)
        except CatalogError as exc:
            # An out-of-range limit/offset surfaced from the domain.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        codes = [product.code.value for product in page.items]
        # When a viewing channel is given, enrich each item with its "from" price
        # and availability so the PLP can show pricing without an extra round-trip.
        channel = data.get("channel")
        summaries = (
            build_summarise_storefront_prices().execute(codes=codes, channel=channel)
            if channel
            else None
        )
        # A primary image (promoted from a variant) is always attached -- it is not
        # channel-scoped and lets the card render a real photo instead of a placeholder.
        images = build_get_storefront_product_images().execute(codes=codes)
        return Response(
            _storefront_page_payload(
                page, limit=query.limit, offset=query.offset, summaries=summaries, images=images
            )
        )


def _window_kwargs(data: dict[str, object]) -> dict[str, int]:
    """Pass limit/offset to the query only when supplied, so the dataclass defaults apply."""
    window: dict[str, int] = {}
    if "limit" in data:
        window["limit"] = data["limit"]  # type: ignore[assignment]
    if "offset" in data:
        window["offset"] = data["offset"]  # type: ignore[assignment]
    return window


class StorefrontProductDetailView(APIView):
    """Public detail of a single published product (the PDP source).

    A draft or unknown product is a 404 alike -- the existence of an unpublished
    product is never revealed to anonymous callers.
    """

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        operation_id="storefront_product_retrieve",
        responses={200: StorefrontProductSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, code: str) -> Response:
        try:
            product = build_get_published_product().execute(code=code)
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        image = build_get_storefront_product_images().execute(codes=[code]).get(code)
        return Response(_storefront_product_payload(product, image=image))


def _storefront_variant_payload(item: StorefrontVariant) -> dict[str, object]:
    """Project a published variant plus its channel price for the storefront.

    Omits the internal ``id`` (the public key is the SKU). The price amount is a
    string so the exact Decimal survives JSON; ``price`` is null when the variant has
    no base price in the requested channel.
    """
    variant = item.variant
    return {
        "sku": variant.sku.value,
        "name": variant.name,
        "values": [
            {"attribute": value.attribute.value, "value": value.value} for value in variant.values
        ],
        "media": [{"url": asset.url, "alt_text": asset.alt_text} for asset in variant.media],
        "price": (
            None
            if item.price is None
            else {"amount": str(item.price.money.amount), "currency": item.price.money.currency}
        ),
    }


class StorefrontProductVariantsView(APIView):
    """Public list of a published product's purchasable variants, priced for a channel.

    The PDP's add-to-cart surface. A draft or unknown product is a 404 (its existence
    is never revealed); a variant with no price in the channel is returned with a null
    price so it can be shown but not purchased there.
    """

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="channel", type=str, location=OpenApiParameter.QUERY, required=True
            )
        ],
        responses={
            200: StorefrontProductVariantsSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, code: str) -> Response:
        params = StorefrontVariantsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        channel = params.validated_data["channel"]
        try:
            variants = build_get_storefront_product_variants().execute(code=code, channel=channel)
        except ProductNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {"channel": channel, "variants": [_storefront_variant_payload(v) for v in variants]}
        )


class StorefrontCategoryListView(APIView):
    """Public list of categories, for the storefront's filter chooser."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(responses=StorefrontCategorySerializer(many=True))
    def get(self, request: Request) -> Response:
        categories = build_list_categories().execute()
        return Response(
            [
                {
                    "slug": category.slug.value,
                    "name": category.name,
                    "parent": category.parent.value if category.parent is not None else None,
                }
                for category in categories
            ]
        )


class StorefrontCollectionListView(APIView):
    """Public list of collections, for the storefront's filter chooser."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(responses=StorefrontCollectionSerializer(many=True))
    def get(self, request: Request) -> Response:
        collections = build_list_collections().execute()
        return Response(
            [{"slug": collection.slug.value, "name": collection.name} for collection in collections]
        )


class StorefrontProductTypeListView(APIView):
    """Public list of product types, for the storefront's filter chooser."""

    permission_classes: ClassVar = [AllowAny]

    @extend_schema(responses=StorefrontProductTypeSerializer(many=True))
    def get(self, request: Request) -> Response:
        product_types = build_list_product_types().execute()
        return Response([{"code": pt.code.value, "name": pt.name} for pt in product_types])


class ProductExportView(APIView):
    """Export every product as a CSV attachment.

    A read, so it follows the catalog's read posture (any authenticated user): the
    same data is already reachable through the management product reads, so gating a
    bulk read more strictly than the per-row reads it duplicates would be theatre.
    The write side (import) is what requires the manage permission.
    """

    permission_classes: ClassVar = [CatalogManagePermission]

    @extend_schema(
        responses={200: OpenApiResponse(OpenApiTypes.STR, description="CSV file of all products")}
    )
    def get(self, request: Request) -> HttpResponse:
        rows = build_export_catalog_products().execute()
        response = HttpResponse(encode_products(rows), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'
        return response


def _import_result_payload(result: ProductImportResult) -> dict[str, object]:
    """Project an import result (created count + per-row errors) to the response body."""
    return {
        "created": result.created,
        "errors": [
            {"row_number": error.row_number, "code": error.code, "error": error.error}
            for error in result.errors
        ],
    }


def _import_file_error(message: str) -> Response:
    """A whole-file failure, shaped like an import result so the body is uniform."""
    payload = {"created": 0, "errors": [{"row_number": 0, "code": "", "error": message}]}
    return Response(payload, status=status.HTTP_400_BAD_REQUEST)


class ProductImportView(APIView):
    """Create products in bulk from an uploaded CSV file (admin, all-or-nothing).

    The response is always import-result shaped: 200 when every row was created, 400
    (with the per-row or whole-file errors) when nothing was -- a partial import is
    impossible.
    """

    permission_classes: ClassVar = [CatalogManagePermission]
    parser_classes: ClassVar = [MultiPartParser]

    @extend_schema(
        request=ProductImportRequestSerializer,
        responses={
            200: ProductImportResultSerializer,
            400: ProductImportResultSerializer,
            403: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return _import_file_error("no file uploaded (expected multipart field 'file')")
        if upload.size > _MAX_IMPORT_BYTES:
            return _import_file_error(f"file exceeds the {_MAX_IMPORT_BYTES}-byte limit")
        try:
            text = upload.read().decode("utf-8")
        except UnicodeDecodeError:
            return _import_file_error("file is not valid UTF-8")
        try:
            rows = decode_products(text)
        except CsvFormatError as exc:
            return _import_file_error(str(exc))
        try:
            result = build_import_catalog_products().execute(rows, actor=_actor(request))
        except CatalogError as exc:
            # An oversized row count, or a rare lost insert race during the write.
            return _import_file_error(str(exc))
        status_code = status.HTTP_200_OK if not result.errors else status.HTTP_400_BAD_REQUEST
        return Response(_import_result_payload(result), status=status_code)
