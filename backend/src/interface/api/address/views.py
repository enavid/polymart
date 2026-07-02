"""Address-book endpoints (thin transport adapters).

Views parse input, delegate to a use case, and serialize the result -- no business
logic. Domain exceptions are translated to HTTP status codes here.

Every route resolves addresses from the authenticated user (``request.user``); there is
no owner id in the request body, and reads are owner-scoped in the repository, so one
shopper can never list, read, edit, delete, or default another's address (IDOR is
structurally impossible). Address ids are opaque and unguessable, so appearing in a URL
leaks nothing. A malformed id can never match an owner's address either, so it is
folded into the same 404 as "not found" -- never surfaced as a distinct 400 -- so the
shape of a valid id is not probed.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.address.use_cases import (
    AddAddressCommand,
    DeleteAddressCommand,
    SetDefaultAddressCommand,
    UpdateAddressCommand,
)
from src.domain.address.entities import Address
from src.domain.address.exceptions import (
    AddressError,
    AddressLimitExceededError,
    AddressNotFoundError,
    InvalidAddressIdError,
)
from src.interface.api.address.container import (
    build_add_address,
    build_delete_address,
    build_list_my_addresses,
    build_set_default_address,
    build_update_address,
)
from src.interface.api.address.serializers import (
    AddressSerializer,
    AddressUpdateSerializer,
    AddressWriteSerializer,
)
from src.interface.api.common import ErrorSerializer

logger = structlog.get_logger(__name__)

_NOT_FOUND_DETAIL = {"detail": "address not found"}
# Malformed ids and not-found-or-not-yours addresses both surface as this pair, so a
# caller cannot distinguish "wrong shape" from "not mine" by status code alone.
_NOT_FOUND_ERRORS = (InvalidAddressIdError, AddressNotFoundError)


def _owner(request: Request) -> str:
    """The authenticated user's stable id -- the address's owner (never the PII username)."""
    return str(request.user.pk)


def _payload(address: Address) -> dict[str, object]:
    """Project an address to the response body."""
    return {
        "id": address.id.value,
        "recipient_name": address.recipient_name.value,
        "phone_number": address.phone_number.value,
        "province": address.province.value,
        "city": address.city.value,
        "postal_code": address.postal_code.value,
        "line1": address.line1.value,
        "line2": address.line2.value if address.line2 else None,
        "is_default": address.is_default,
        "created_at": address.created_at,
    }


class AddressCollectionView(APIView):
    """List the authenticated shopper's address book, or save a new address."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        operation_id="addresses_list",
        responses={200: AddressSerializer(many=True), 401: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        addresses = build_list_my_addresses().execute(_owner(request))
        return Response([_payload(address) for address in addresses])

    @extend_schema(
        operation_id="addresses_create",
        request=AddressWriteSerializer,
        responses={
            201: AddressSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AddressWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = AddAddressCommand(
            owner=_owner(request),
            recipient_name=data["recipient_name"],
            phone_number=data["phone_number"],
            province=data["province"],
            city=data["city"],
            postal_code=data["postal_code"],
            line1=data["line1"],
            line2=data.get("line2") or None,
            is_default=data.get("is_default", False),
        )
        try:
            address = build_add_address().execute(command)
        except AddressLimitExceededError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except AddressError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_payload(address), status=status.HTTP_201_CREATED)


class AddressDetailView(APIView):
    """Edit or delete one of the authenticated shopper's saved addresses."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        operation_id="addresses_update",
        request=AddressUpdateSerializer,
        responses={
            200: AddressSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def put(self, request: Request, address_id: str) -> Response:
        serializer = AddressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        command = UpdateAddressCommand(
            owner=_owner(request),
            address_id=address_id,
            recipient_name=data["recipient_name"],
            phone_number=data["phone_number"],
            province=data["province"],
            city=data["city"],
            postal_code=data["postal_code"],
            line1=data["line1"],
            line2=data.get("line2") or None,
        )
        try:
            address = build_update_address().execute(command)
        except _NOT_FOUND_ERRORS as exc:
            logger.debug("address_lookup_rejected", detail=str(exc))
            return Response(_NOT_FOUND_DETAIL, status=status.HTTP_404_NOT_FOUND)
        except AddressError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_payload(address))

    @extend_schema(
        operation_id="addresses_delete",
        request=None,
        responses={204: None, 401: ErrorSerializer, 404: ErrorSerializer},
    )
    def delete(self, request: Request, address_id: str) -> Response:
        try:
            build_delete_address().execute(
                DeleteAddressCommand(owner=_owner(request), address_id=address_id)
            )
        except _NOT_FOUND_ERRORS as exc:
            logger.debug("address_lookup_rejected", detail=str(exc))
            return Response(_NOT_FOUND_DETAIL, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AddressSetDefaultView(APIView):
    """Mark one of the authenticated shopper's addresses as their default."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(
        operation_id="addresses_set_default",
        request=None,
        responses={200: AddressSerializer, 401: ErrorSerializer, 404: ErrorSerializer},
    )
    def post(self, request: Request, address_id: str) -> Response:
        try:
            address = build_set_default_address().execute(
                SetDefaultAddressCommand(owner=_owner(request), address_id=address_id)
            )
        except _NOT_FOUND_ERRORS as exc:
            logger.debug("address_lookup_rejected", detail=str(exc))
            return Response(_NOT_FOUND_DETAIL, status=status.HTTP_404_NOT_FOUND)
        return Response(_payload(address))
