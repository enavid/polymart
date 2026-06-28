"""Serializers for the audit read endpoint (transport shaping only)."""

from __future__ import annotations

from rest_framework import serializers


class AuditEntrySerializer(serializers.Serializer):
    """Response projection of one audit entry.

    Documents the response shape in the OpenAPI schema; the view projects the
    domain ``AuditEntry`` to this shape directly (its value objects cannot be fed
    to a serializer).
    """

    action = serializers.CharField()
    resource_type = serializers.CharField()
    resource_id = serializers.CharField()
    actor = serializers.CharField(allow_null=True)
    occurred_at = serializers.DateTimeField()
    # {field: {"before": <scalar|null>, "after": <scalar|null>}} per changed field.
    changes = serializers.JSONField()
