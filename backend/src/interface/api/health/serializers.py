"""Serializers for the health endpoint (response shaping only)."""
from __future__ import annotations

from rest_framework import serializers


class ComponentHealthSerializer(serializers.Serializer):
    name = serializers.CharField()
    state = serializers.CharField()
    detail = serializers.CharField(allow_blank=True)


class HealthReportSerializer(serializers.Serializer):
    state = serializers.CharField()
    components = ComponentHealthSerializer(many=True)
