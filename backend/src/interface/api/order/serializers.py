"""Serializers for the order endpoints (transport shaping only).

Format validation (sku/quantity/money rules) is owned by the domain, so these
serializers stay thin: presence/type checks on input, field projection on output. Money
is projected as a string so the exact ``Decimal`` survives JSON.
"""

from __future__ import annotations

from rest_framework import serializers


class PlaceOrderSerializer(serializers.Serializer):
    """Request body for placing an order (checking out the channel's cart)."""

    channel = serializers.CharField()


class OrderListQuerySerializer(serializers.Serializer):
    """Query parameters for paging a shopper's order history."""

    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)


class OrderLineSerializer(serializers.Serializer):
    """Response projection of one captured order line (money as exact strings)."""

    sku = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.CharField()
    line_total = serializers.CharField()


class OrderSerializer(serializers.Serializer):
    """Response projection of a placed order."""

    number = serializers.CharField()
    channel = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    total = serializers.CharField()
    placed_at = serializers.DateTimeField()
    items = OrderLineSerializer(many=True)


class OrderPageSerializer(serializers.Serializer):
    """Response projection of one page of a shopper's orders."""

    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = OrderSerializer(many=True)
