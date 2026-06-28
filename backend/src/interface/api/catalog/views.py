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
    CreateAttributeCommand,
    CreateProductTypeCommand,
)
from src.domain.catalog.entities import Attribute, ProductType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
    CatalogError,
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
)
from src.interface.api.access.permissions import CatalogManagePermission
from src.interface.api.catalog.container import (
    build_create_attribute,
    build_create_product_type,
    build_get_attribute,
    build_get_product_type,
    build_list_attributes,
    build_list_product_types,
)
from src.interface.api.catalog.serializers import (
    AttributeSerializer,
    CreateAttributeSerializer,
    CreateProductTypeSerializer,
    ProductTypeSerializer,
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
        "choices": [
            {"value": choice.value, "label": choice.label} for choice in attribute.choices
        ],
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
