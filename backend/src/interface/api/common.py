"""Shared transport-layer serializers used across API contexts."""

from __future__ import annotations

from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """The standard error body returned by views: ``{"detail": "..."}``."""

    detail = serializers.CharField()
