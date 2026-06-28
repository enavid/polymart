"""Serializers for the identity/auth endpoints (transport shaping only)."""

from __future__ import annotations

from rest_framework import serializers

from src.domain.identity.enums import OtpPurpose

# Minimum password length enforced at the edge; the domain stays password-agnostic.
_MIN_PASSWORD_LENGTH = 8


class LoginSerializer(serializers.Serializer):
    """Request body for logging in."""

    phone_number = serializers.CharField()
    # write_only so the password is never reflected back in any response.
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class RequestOtpSerializer(serializers.Serializer):
    """Request body for requesting a one-time code."""

    phone_number = serializers.CharField()
    purpose = serializers.ChoiceField(choices=[purpose.value for purpose in OtpPurpose])


class RegisterSerializer(serializers.Serializer):
    """Request body for completing registration with a one-time code."""

    phone_number = serializers.CharField()
    # write_only: the code is a credential and must never echo back.
    code = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True, min_length=_MIN_PASSWORD_LENGTH, style={"input_type": "password"}
    )
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class PasswordResetSerializer(serializers.Serializer):
    """Request body for setting a new password with a one-time code."""

    phone_number = serializers.CharField()
    code = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True, min_length=_MIN_PASSWORD_LENGTH, style={"input_type": "password"}
    )


class UserSerializer(serializers.Serializer):
    """Response projection of the authenticated user (no secrets)."""

    id = serializers.IntegerField(read_only=True)
    phone_number = serializers.CharField()
    email = serializers.CharField()
    full_name = serializers.CharField()
    is_staff = serializers.BooleanField()
