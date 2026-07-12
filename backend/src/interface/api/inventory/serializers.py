"""Serializers for the inventory admin endpoints (transport shaping only).

Thin presence/type checks on input and documentation of the response shape. The domain
value objects enforce the real rules (code shape, non-negative quantity), surfaced as a
400 by the view; authorization is the permission class's job.
"""

from __future__ import annotations

from rest_framework import serializers


class StockSourceSerializer(serializers.Serializer):
    """Response projection of a stock source (warehouse)."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class CreateStockSourceSerializer(serializers.Serializer):
    """Request body for creating a stock source."""

    code = serializers.CharField()
    name = serializers.CharField()


class SourceStockSerializer(serializers.Serializer):
    """Response projection of a variant's stock at one source."""

    sku = serializers.CharField()
    source_code = serializers.CharField()
    on_hand = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()


class SetStockSerializer(serializers.Serializer):
    """Request body for setting a variant's on-hand at a source to an absolute value."""

    quantity = serializers.IntegerField(min_value=0)


class AdjustStockSerializer(serializers.Serializer):
    """Request body for applying a signed delta to a variant's on-hand at a source."""

    delta = serializers.IntegerField()


class StockPolicySerializer(serializers.Serializer):
    """Response projection of a variant's selling policy."""

    sku = serializers.CharField()
    backorderable = serializers.BooleanField()
    low_stock_threshold = serializers.IntegerField()
    backordered = serializers.IntegerField()


class SetStockPolicySerializer(serializers.Serializer):
    """Request body for setting a variant's selling policy."""

    backorderable = serializers.BooleanField()
    low_stock_threshold = serializers.IntegerField(min_value=0)
