"""Serializers for the order endpoints (transport shaping only).

Format validation (sku/quantity/money rules) is owned by the domain, so these
serializers stay thin: presence/type checks on input, field projection on output. Money
is projected as a string so the exact ``Decimal`` survives JSON.
"""

from __future__ import annotations

import re

from rest_framework import serializers

# Iranian mobile + 10-digit postal formats, mirroring the address context's value objects
# (a guest's inline address is not validated by that context, so the transport re-checks
# the same shapes here rather than letting a malformed address reach the domain).
_IRAN_MOBILE_RE = re.compile(r"^09\d{9}$")
_POSTAL_CODE_RE = re.compile(r"^\d{10}$")


class InlineShippingAddressSerializer(serializers.Serializer):
    """Request body for a guest's one-off shipping address, captured inline at checkout.

    A guest has no address book, so the fields are supplied directly. Phone and postal
    formats are validated here (the address context that normally owns those rules is not
    on a guest's path); presence/length is re-checked by the order's value object.
    """

    recipient_name = serializers.CharField(max_length=200)
    phone_number = serializers.RegexField(_IRAN_MOBILE_RE)
    province = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    postal_code = serializers.RegexField(_POSTAL_CODE_RE)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PlaceOrderSerializer(serializers.Serializer):
    """Request body for placing an order (checking out the channel's cart).

    Exactly one shipping source is required: a signed-in shopper sends ``address_id`` (one
    of their saved addresses, resolved and snapshotted by the use case), while a guest
    sends a one-off ``shipping_address`` inline. Sending both or neither is rejected.
    """

    channel = serializers.CharField()
    shipping_method = serializers.CharField()
    address_id = serializers.CharField(required=False)
    shipping_address = InlineShippingAddressSerializer(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        has_id = attrs.get("address_id") is not None
        has_inline = attrs.get("shipping_address") is not None
        if has_id == has_inline:
            raise serializers.ValidationError(
                "provide exactly one of 'address_id' or 'shipping_address'."
            )
        return attrs


class ManualOrderItemSerializer(serializers.Serializer):
    """One staff-specified line of a manual order (sku + a positive quantity)."""

    sku = serializers.CharField(max_length=64)
    quantity = serializers.IntegerField(min_value=1)


class ManualOrderSerializer(serializers.Serializer):
    """Request body for a staff member creating a manual order (a pre-invoice).

    The lines are supplied directly (no cart) and the customer's shipping address is
    captured inline. At least one line is required and a variant may appear at most once;
    the domain re-validates prices/stock and the total.
    """

    channel = serializers.CharField()
    items = ManualOrderItemSerializer(many=True, allow_empty=False)
    shipping_address = InlineShippingAddressSerializer()

    def validate_items(self, value: list[dict[str, object]]) -> list[dict[str, object]]:
        skus = [item["sku"] for item in value]
        if len(skus) != len(set(skus)):
            raise serializers.ValidationError("a variant may appear on only one line.")
        return value


class ShippingAddressSerializer(serializers.Serializer):
    """Response projection of an order's captured shipping address."""

    recipient_name = serializers.CharField()
    phone_number = serializers.CharField()
    province = serializers.CharField()
    city = serializers.CharField()
    postal_code = serializers.CharField()
    line1 = serializers.CharField()
    line2 = serializers.CharField(allow_null=True)


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
    """Response projection of a placed order.

    ``total`` is the grand total (goods + shipping + tax); ``subtotal`` is the goods total,
    ``shipping_cost`` the delivery charge, and ``tax`` the tax amount (money as exact strings).
    ``shipping_method``/``shipping_method_name`` are ``null`` for an order with no delivery
    charge; ``tax``/``tax_rate`` are ``null`` for an order in an untaxed channel.
    """

    number = serializers.CharField()
    channel = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    subtotal = serializers.CharField()
    shipping_cost = serializers.CharField()
    shipping_method = serializers.CharField(allow_null=True)
    shipping_method_name = serializers.CharField(allow_null=True)
    tax = serializers.CharField(allow_null=True)
    tax_rate = serializers.CharField(allow_null=True)
    total = serializers.CharField()
    placed_at = serializers.DateTimeField()
    items = OrderLineSerializer(many=True)
    shipping_address = ShippingAddressSerializer()


class OrderPageSerializer(serializers.Serializer):
    """Response projection of one page of a shopper's orders."""

    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = OrderSerializer(many=True)


class PreInvoiceSerializer(OrderSerializer):
    """Response projection of an order's pre-invoice (proforma).

    The full order (which already carries ``tax``/``tax_rate``) plus a ``document_type`` marker
    and a ``grand_total`` (equal to the order total, which includes the tax).
    """

    document_type = serializers.CharField()
    grand_total = serializers.CharField()
