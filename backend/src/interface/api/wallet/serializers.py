"""Serializers for the wallet endpoint (transport shaping only).

Thin: the domain owns money validation, so these only project the read model. Amounts are
projected as exact strings so the ``Decimal`` survives JSON and is never parsed into a float.
"""

from __future__ import annotations

from rest_framework import serializers


class WalletTransactionSerializer(serializers.Serializer):
    """Response projection of one wallet ledger entry (amounts as exact strings)."""

    type = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    reason = serializers.CharField()
    balance_after = serializers.CharField()
    source_reference = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()


class WalletSerializer(serializers.Serializer):
    """Response projection of a wallet: the balance plus its recent statement."""

    balance = serializers.CharField()
    currency = serializers.CharField()
    transactions = WalletTransactionSerializer(many=True)
