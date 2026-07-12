"""Inventory admin endpoints (thin transport adapters).

List/create stock sources (warehouses) and read/set/adjust a variant's physical on-hand
at one source. Creating a source needs the global ``manage_stock_source`` permission;
mutating a source's stock is authorised either globally *or* by a per-source guardian
grant (two-layer RBAC), enforced by resolving the source and calling
``check_object_permissions``. Views hold no business logic -- they parse, delegate to an
audited use case, and map domain exceptions to HTTP status codes.
"""

from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.inventory.use_cases import (
    CreateStockSourceCommand,
    SetStockPolicyCommand,
    SourceStock,
)
from src.domain.catalog.exceptions import VariantNotFoundError
from src.domain.inventory.entities import StockPolicy, StockSource
from src.domain.inventory.exceptions import (
    InsufficientStockError,
    InventoryError,
    StockSourceAlreadyExistsError,
    StockSourceNotFoundError,
)
from src.domain.inventory.value_objects import StockSourceCode
from src.interface.api.access.permissions import (
    GlobalStockSourceManagePermission,
    ScopedStockSourceManagePermission,
)
from src.interface.api.catalog.container import build_get_variant
from src.interface.api.common import ErrorSerializer
from src.interface.api.inventory.container import (
    build_adjust_stock_on_hand,
    build_create_stock_source,
    build_get_source_stock,
    build_get_stock_policy,
    build_get_stock_source,
    build_list_stock_sources,
    build_set_stock_on_hand,
    build_set_stock_policy,
)
from src.interface.api.inventory.serializers import (
    AdjustStockSerializer,
    CreateStockSourceSerializer,
    SetStockPolicySerializer,
    SetStockSerializer,
    SourceStockSerializer,
    StockPolicySerializer,
    StockSourceSerializer,
)


def _actor(request: Request) -> str | None:
    """Identify the acting administrator for the audit trail (stable id, not PII)."""
    user = request.user
    return str(user.pk) if user.is_authenticated else None


def _source_payload(source: StockSource) -> dict[str, object]:
    return {"id": source.id, "code": source.code.value, "name": source.name}


def _stock_payload(stock: SourceStock) -> dict[str, object]:
    return {
        "sku": stock.sku,
        "source_code": stock.source_code,
        "on_hand": stock.on_hand,
        "reserved": stock.reserved,
        "available": stock.available,
    }


def _policy_payload(policy: StockPolicy) -> dict[str, object]:
    return {
        "sku": policy.sku,
        "backorderable": policy.backorderable,
        "low_stock_threshold": policy.low_stock_threshold,
        "backordered": policy.backordered.value,
    }


class StockSourceListCreateView(APIView):
    """List stock sources or create a new one."""

    permission_classes: ClassVar = [GlobalStockSourceManagePermission]

    @extend_schema(responses=StockSourceSerializer(many=True))
    def get(self, request: Request) -> Response:
        sources = build_list_stock_sources().execute()
        return Response([_source_payload(source) for source in sources])

    @extend_schema(
        request=CreateStockSourceSerializer,
        responses={
            201: StockSourceSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CreateStockSourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            source = build_create_stock_source().execute(
                CreateStockSourceCommand(code=data["code"], name=data["name"]),
                actor=_actor(request),
            )
        except StockSourceAlreadyExistsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except InventoryError as exc:
            # A malformed code or name surfaced from the domain value objects/entity.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_source_payload(source), status=status.HTTP_201_CREATED)


class SourceStockView(APIView):
    """Read, set, or adjust a variant's physical on-hand stock at one source."""

    permission_classes: ClassVar = [ScopedStockSourceManagePermission]

    def _resolve_source(self, code: str) -> StockSource:
        """Resolve the target source (a 404 if missing) for the object-scope check."""
        return build_get_stock_source().execute(code=code)

    @extend_schema(responses={200: SourceStockSerializer, 404: ErrorSerializer})
    def get(self, request: Request, code: str, sku: str) -> Response:
        try:
            self._resolve_source(code)
            build_get_variant().execute(sku=sku)
        except (StockSourceNotFoundError, VariantNotFoundError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        stock = build_get_source_stock().execute(sku=sku, source_code=StockSourceCode(code))
        return Response(_stock_payload(stock))

    @extend_schema(
        request=SetStockSerializer,
        responses={
            200: SourceStockSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def put(self, request: Request, code: str, sku: str) -> Response:
        serializer = SetStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            source = self._resolve_source(code)
            build_get_variant().execute(sku=sku)
        except (StockSourceNotFoundError, VariantNotFoundError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        # Enforce object-level scope only after the target resolves (a missing source is a
        # 404, not a 403): a per-source manager may mutate only that source.
        self.check_object_permissions(request, source)
        try:
            build_set_stock_on_hand().execute(
                sku=sku,
                source_code=StockSourceCode(code),
                quantity=serializer.validated_data["quantity"],
                actor=_actor(request),
            )
        except InsufficientStockError as exc:
            # Setting below what is already reserved is a conflict, not a bad request.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return self._current_stock(code, sku)

    @extend_schema(
        request=AdjustStockSerializer,
        responses={
            200: SourceStockSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def patch(self, request: Request, code: str, sku: str) -> Response:
        serializer = AdjustStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            source = self._resolve_source(code)
            build_get_variant().execute(sku=sku)
        except (StockSourceNotFoundError, VariantNotFoundError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        self.check_object_permissions(request, source)
        try:
            build_adjust_stock_on_hand().execute(
                sku=sku,
                source_code=StockSourceCode(code),
                delta=serializer.validated_data["delta"],
                actor=_actor(request),
            )
        except InsufficientStockError as exc:
            # An over-withdrawal (below zero / below reserved) is a conflict.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return self._current_stock(code, sku)

    def _current_stock(self, code: str, sku: str) -> Response:
        stock = build_get_source_stock().execute(sku=sku, source_code=StockSourceCode(code))
        return Response(_stock_payload(stock))


class VariantStockPolicyView(APIView):
    """Read or set a variant's selling policy (backorder flag + low-stock threshold).

    The policy is platform-global (not per-source) configuration, so management requires
    the global ``manage_stock_source`` permission -- never object-scoped. The SKU is
    validated against the catalog so a policy is never set for a non-existent variant.
    """

    permission_classes: ClassVar = [GlobalStockSourceManagePermission]

    @extend_schema(responses={200: StockPolicySerializer, 404: ErrorSerializer})
    def get(self, request: Request, sku: str) -> Response:
        try:
            build_get_variant().execute(sku=sku)
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        policy = build_get_stock_policy().execute(sku=sku)
        return Response(_policy_payload(policy))

    @extend_schema(
        request=SetStockPolicySerializer,
        responses={
            200: StockPolicySerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, sku: str) -> Response:
        serializer = SetStockPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            build_get_variant().execute(sku=sku)
        except VariantNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        data = serializer.validated_data
        policy = build_set_stock_policy().execute(
            SetStockPolicyCommand(
                sku=sku,
                backorderable=data["backorderable"],
                low_stock_threshold=data["low_stock_threshold"],
            ),
            actor=_actor(request),
        )
        return Response(_policy_payload(policy))
