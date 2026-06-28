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


class ProductTypeSerializer(serializers.Serializer):
    """Response projection of a product type."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField()
    name = serializers.CharField()
    attributes = serializers.ListField(child=serializers.CharField())
    variant_attributes = serializers.ListField(child=serializers.CharField())


class CreateProductTypeSerializer(serializers.Serializer):
    """Request body for creating a product type."""

    code = serializers.CharField()
    name = serializers.CharField()
    attributes = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    variant_attributes = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )


class AttributeValueSerializer(serializers.Serializer):
    """One attribute value carried by a product."""

    attribute = serializers.CharField()
    value = serializers.CharField()


class ProductSerializer(serializers.Serializer):
    """Response projection of a product."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField()
    name = serializers.CharField()
    product_type = serializers.CharField()
    values = AttributeValueSerializer(many=True)
    metadata = serializers.DictField(child=serializers.CharField())


class CreateProductSerializer(serializers.Serializer):
    """Request body for creating a product."""

    code = serializers.CharField()
    name = serializers.CharField()
    product_type = serializers.CharField()
    values = AttributeValueSerializer(many=True, required=False, default=list)
    metadata = serializers.DictField(child=serializers.CharField(), required=False, default=dict)


class VariantMediaSerializer(serializers.Serializer):
    """One media asset (image) attached to a variant."""

    url = serializers.CharField()
    alt_text = serializers.CharField(required=False, default="", allow_blank=True)


class VariantSerializer(serializers.Serializer):
    """Response projection of a product variant."""

    id = serializers.IntegerField(read_only=True)
    product = serializers.CharField()
    sku = serializers.CharField()
    name = serializers.CharField()
    values = AttributeValueSerializer(many=True)
    media = VariantMediaSerializer(many=True)


class CreateVariantSerializer(serializers.Serializer):
    """Request body for creating a variant (the parent product comes from the URL)."""

    sku = serializers.CharField()
    name = serializers.CharField()
    values = AttributeValueSerializer(many=True, required=False, default=list)
    media = VariantMediaSerializer(many=True, required=False, default=list)
