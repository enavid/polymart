"""Catalog endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result. They hold no
business logic. Domain exceptions are translated to HTTP status codes here -- the
one place where the domain meets the transport.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.catalog.use_cases import (
    AttributeChoiceInput,
    AttributeValueInput,
    CreateAttributeCommand,
    CreateCategoryCommand,
    CreateCollectionCommand,
    CreateProductCommand,
    CreateProductTypeCommand,
    CreateVariantCommand,
    MediaInput,
    RuleConditionInput,
    SetCollectionProductsCommand,
    SetCollectionRuleCommand,
    SetProductCategoriesCommand,
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
from src.domain.catalog.value_objects import CategorySlug, ProductCode, RuleCondition
from src.interface.api.access.permissions import CatalogManagePermission
from src.interface.api.catalog.container import (
    build_create_attribute,
    build_create_category,
    build_create_collection,
    build_create_product,
    build_create_product_type,
    build_create_variant,
    build_get_attribute,
    build_get_category,
    build_get_collection,
    build_get_collection_products,
    build_get_collection_rule,
    build_get_collection_rule_members,
    build_get_product,
    build_get_product_categories,
    build_get_product_type,
    build_get_variant,
    build_list_attributes,
    build_list_categories,
    build_list_collections,
    build_list_product_types,
    build_list_product_variants,
    build_list_products,
    build_set_collection_products,
    build_set_collection_rule,
    build_set_product_categories,
)
from src.interface.api.catalog.serializers import (
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
    ProductSerializer,
    ProductTypeSerializer,
    VariantSerializer,
)
from src.interface.api.common import ErrorSerializer

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
