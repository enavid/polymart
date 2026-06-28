"""Audit read endpoint (thin transport adapter).

Lists recent audit entries, optionally filtered by resource/action. Reading the
trail is a security-oversight action, so it is gated by the same global
``manage_access`` permission as the rest of access administration. The view holds
no business logic: it parses query params, delegates to the read use case, and
projects the domain entries to JSON.
"""

from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.domain.audit.entities import AuditEntry
from src.interface.api.access.permissions import AccessAdminPermission
from src.interface.api.audit.container import build_list_audit_entries
from src.interface.api.audit.serializers import AuditEntrySerializer


def _int_or_none(raw: str | None) -> int | None:
    """Parse an optional integer query param, ignoring non-numeric input.

    A malformed ``limit`` falls back to the use case's default rather than 400 --
    the caller gets a sane page instead of an error.
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _payload(entry: AuditEntry) -> dict[str, object]:
    return {
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "actor": entry.actor,
        "occurred_at": entry.occurred_at,
        "changes": {
            change.field: {"before": change.before, "after": change.after}
            for change in entry.changes
        },
    }


class AuditLogView(APIView):
    """List recent audit entries (newest first)."""

    permission_classes: ClassVar = [AccessAdminPermission]

    @extend_schema(
        parameters=[
            OpenApiParameter("resource_type", str, description="Filter by resource type."),
            OpenApiParameter("resource_id", str, description="Filter by resource id."),
            OpenApiParameter("action", str, description="Filter by action."),
            OpenApiParameter("limit", int, description="Max entries (default 50, max 200)."),
        ],
        responses=AuditEntrySerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        params = request.query_params
        entries = build_list_audit_entries().execute(
            resource_type=params.get("resource_type"),
            resource_id=params.get("resource_id"),
            action=params.get("action"),
            limit=_int_or_none(params.get("limit")),
        )
        return Response([_payload(entry) for entry in entries])
