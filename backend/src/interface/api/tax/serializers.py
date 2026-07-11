"""Serializers for the tax endpoints (transport shaping only).

Format validation is owned by the domain, so these stay thin. The rate is projected as a
string so the exact ``Decimal`` survives JSON (the storefront displays the server's value,
never a recomputed one); it is ``null`` for a channel that levies no tax.
"""

from __future__ import annotations

from rest_framework import serializers


class TaxRateQuerySerializer(serializers.Serializer):
    """Query parameters for reading a channel's tax rate."""

    channel = serializers.CharField()


class TaxRateSerializer(serializers.Serializer):
    """Response projection of a channel's tax rate (percentage as an exact string, or null)."""

    channel = serializers.CharField()
    rate = serializers.CharField(allow_null=True)
