"""Serializers for the cart endpoints (transport shaping only).

Format validation (sku/quantity/channel rules) is owned by the domain, so these
serializers stay deliberately thin: presence/type checks on input, field projection
on output. Money is projected as a string so the exact ``Decimal`` survives JSON.
"""

from __future__ import annotations

from rest_framework import serializers


class CartChannelQuerySerializer(serializers.Serializer):
    """Query parameter selecting the channel a cart is read/removed in."""

    channel = serializers.CharField()


class AddCartItemSerializer(serializers.Serializer):
    """Request body for adding (or incrementing) a cart line."""

    channel = serializers.CharField()
    sku = serializers.CharField()
    quantity = serializers.IntegerField()


class UpdateCartItemSerializer(serializers.Serializer):
    """Request body for setting an existing line's absolute quantity."""

    channel = serializers.CharField()
    quantity = serializers.IntegerField()


class PricedLineSerializer(serializers.Serializer):
    """Response projection of one priced cart line.

    ``unit_price`` and ``line_total`` are strings (exact Decimal) or ``null`` when
    the line is unavailable (its variant has no price in the channel).
    """

    sku = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.CharField(allow_null=True)
    line_total = serializers.CharField(allow_null=True)
    available = serializers.BooleanField()


class PricedCartSerializer(serializers.Serializer):
    """Response projection of a priced cart."""

    channel = serializers.CharField()
    currency = serializers.CharField()
    items = PricedLineSerializer(many=True)
    total = serializers.CharField()
