"""Serializers for the identity/auth endpoints (transport shaping only)."""

from __future__ import annotations

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    """Request body for logging in."""

    phone_number = serializers.CharField()
    # write_only so the password is never reflected back in any response.
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class UserSerializer(serializers.Serializer):
    """Response projection of the authenticated user (no secrets)."""

    id = serializers.IntegerField(read_only=True)
    phone_number = serializers.CharField()
    email = serializers.CharField()
    full_name = serializers.CharField()
    is_staff = serializers.BooleanField()
