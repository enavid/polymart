"""Serializers for the payment endpoints (transport shaping only).

Format validation of the domain (amount/reference rules) is owned by the domain, so these
serializers stay thin: presence/type checks on input, field projection on output. The
amount is projected as a string so the exact ``Decimal`` survives JSON and is never parsed
into a float.
"""

from __future__ import annotations

from rest_framework import serializers

from src.domain.payment.value_objects import PaymentMethod

# The methods a shopper may choose. All enum members are accepted at the transport; the
# use case rejects one with no registered gateway (UnsupportedPaymentMethodError -> 400),
# so "recognised but not yet available" is distinct from "not a method at all".
_METHOD_CHOICES = [method.value for method in PaymentMethod]


class InitiatePaymentSerializer(serializers.Serializer):
    """Request body for initiating a payment against one of the shopper's own orders."""

    order_number = serializers.CharField(max_length=40)
    method = serializers.ChoiceField(choices=_METHOD_CHOICES)


class PaymentSerializer(serializers.Serializer):
    """Response projection of a payment (amount as an exact string)."""

    reference = serializers.CharField()
    order_number = serializers.CharField()
    method = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class PaymentInitiationSerializer(PaymentSerializer):
    """Response projection of an initiated payment: the payment plus what to do next.

    ``next_action`` is ``none`` for an offline method (COD -- just show a confirmation) or
    ``redirect`` for an online gateway (a later slice), in which case ``redirect_url`` is
    set. It is ``null`` for COD today.
    """

    next_action = serializers.CharField()
    redirect_url = serializers.CharField(allow_null=True)
