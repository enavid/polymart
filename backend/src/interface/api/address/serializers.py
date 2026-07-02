"""Serializers for the address-book endpoints (transport shaping only).

Format validation (name/phone/postal-code rules) is owned by the domain, so these
serializers stay thin: presence/type checks on input, field projection on output.
"""

from __future__ import annotations

from rest_framework import serializers


class AddressWriteSerializer(serializers.Serializer):
    """Request body for saving a new address."""

    recipient_name = serializers.CharField()
    phone_number = serializers.CharField()
    province = serializers.CharField()
    city = serializers.CharField()
    postal_code = serializers.CharField()
    line1 = serializers.CharField()
    line2 = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    is_default = serializers.BooleanField(required=False, default=False)


class AddressUpdateSerializer(serializers.Serializer):
    """Request body for editing an existing address (default status is a separate action)."""

    recipient_name = serializers.CharField()
    phone_number = serializers.CharField()
    province = serializers.CharField()
    city = serializers.CharField()
    postal_code = serializers.CharField()
    line1 = serializers.CharField()
    line2 = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class AddressSerializer(serializers.Serializer):
    """Response projection of a saved address."""

    id = serializers.CharField()
    recipient_name = serializers.CharField()
    phone_number = serializers.CharField()
    province = serializers.CharField()
    city = serializers.CharField()
    postal_code = serializers.CharField()
    line1 = serializers.CharField()
    line2 = serializers.CharField(allow_null=True)
    is_default = serializers.BooleanField()
    created_at = serializers.DateTimeField()
