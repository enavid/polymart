"""Serializers for the access-administration endpoints (transport shaping only).

Thin presence/type checks on input. The real authorization decision is the
permission class; role/channel existence is enforced by the use case + gateway.
"""

from __future__ import annotations

from rest_framework import serializers


class AssignRoleSerializer(serializers.Serializer):
    """Request body for assigning a global role to a user."""

    user_id = serializers.IntegerField(min_value=1)
    role = serializers.CharField()


class GrantChannelManagementSerializer(serializers.Serializer):
    """Request body for granting a user object-scoped channel management."""

    user_id = serializers.IntegerField(min_value=1)
    channel_slug = serializers.CharField()
