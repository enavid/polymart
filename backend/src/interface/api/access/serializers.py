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


class UserAccountSerializer(serializers.Serializer):
    """Response projection of a user account for the access-admin picker."""

    id = serializers.IntegerField()
    phone_number = serializers.CharField()
    full_name = serializers.CharField(allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    is_staff = serializers.BooleanField()
    is_active = serializers.BooleanField()


class UserAccountPageSerializer(serializers.Serializer):
    """A page of user accounts: the count, the window, and the items."""

    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = UserAccountSerializer(many=True)


class UserListQuerySerializer(serializers.Serializer):
    """Query-string parameters for the user list (pagination bounds only).

    Bounds are enforced by the use case, so an out-of-range page surfaces as a
    domain 400; this layer only checks the types.
    """

    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)


class CreateUserSerializer(serializers.Serializer):
    """Request body for an admin creating a user account directly.

    The password is write-only so it can never be echoed back in a response.
    """

    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(required=False, default="", allow_blank=True)
    email = serializers.CharField(required=False, default="", allow_blank=True)
    is_staff = serializers.BooleanField(required=False, default=False)
