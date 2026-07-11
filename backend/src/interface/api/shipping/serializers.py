"""Serializers for the shipping endpoints (transport shaping only).

Format validation is owned by the domain, so these stay thin. The price is projected as a
string so the exact ``Decimal`` survives JSON (the storefront displays the server's value,
never a recomputed one).
"""

from __future__ import annotations

from rest_framework import serializers


class ShippingMethodsQuerySerializer(serializers.Serializer):
    """Query parameters for listing a channel's shipping methods.

    ``province``/``city`` are optional: when a province is given, each method's price is
    resolved for the zone it falls into; without one, the default rates are returned.
    """

    channel = serializers.CharField()
    province = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)


class ShippingMethodSerializer(serializers.Serializer):
    """Response projection of one offered shipping method (price as an exact string)."""

    code = serializers.CharField()
    name = serializers.CharField()
    price = serializers.CharField()
    currency = serializers.CharField()
    min_days = serializers.IntegerField()
    max_days = serializers.IntegerField()


class ShippingMethodsSerializer(serializers.Serializer):
    """Response projection of a channel's offered shipping methods."""

    channel = serializers.CharField()
    methods = ShippingMethodSerializer(many=True)
