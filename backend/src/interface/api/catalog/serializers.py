"""Serializers for the catalog endpoints (transport shaping only).

Format validation (code/choice slug rules, choice/input-type coherence) is owned
by the domain, so these serializers stay thin: presence/type checks on input,
field projection on output.
"""

from __future__ import annotations

from rest_framework import serializers


class AttributeChoiceSerializer(serializers.Serializer):
    """One option of a choice-type attribute."""

    value = serializers.CharField()
    label = serializers.CharField()


class AttributeSerializer(serializers.Serializer):
    """Response projection of an attribute definition."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField()
    name = serializers.CharField()
    input_type = serializers.CharField()
    required = serializers.BooleanField()
    choices = AttributeChoiceSerializer(many=True)


class CreateAttributeSerializer(serializers.Serializer):
    """Request body for creating an attribute."""

    code = serializers.CharField()
    name = serializers.CharField()
    input_type = serializers.CharField()
    required = serializers.BooleanField(required=False, default=False)
    choices = AttributeChoiceSerializer(many=True, required=False, default=list)
