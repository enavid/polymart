"""Serializers for the channel endpoints (transport shaping only).

Format validation (slug/currency rules) is owned by the domain, so these
serializers stay deliberately thin: presence/type checks on input, field
projection on output.
"""
from __future__ import annotations

from rest_framework import serializers


class ChannelSerializer(serializers.Serializer):
    """Response projection of a channel."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField()
    is_active = serializers.BooleanField()


class CreateChannelSerializer(serializers.Serializer):
    """Request body for creating a channel."""

    slug = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField()
    is_active = serializers.BooleanField(required=False, default=True)


class SetChannelStatusSerializer(serializers.Serializer):
    """Request body for activating/deactivating a channel."""

    is_active = serializers.BooleanField()
