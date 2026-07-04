"""Serializers for the catalog endpoints (transport shaping only).

Format validation (code/choice slug rules, choice/input-type coherence) is owned
by the domain, so these serializers stay thin: presence/type checks on input,
field projection on output.
"""

from __future__ import annotations

from rest_framework import serializers

# Fixed-point money bounds for transport validation (mirrors the Money value object
# and the stored column). The domain remains the source of truth for the positivity
# and currency rules; these only shape/reject the request at the edge.
_AMOUNT_MAX_DIGITS = 18
_AMOUNT_DECIMAL_PLACES = 4


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
    attributes = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    variant_attributes = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )


class AttributeValueSerializer(serializers.Serializer):
    """One attribute value carried by a product."""

    attribute = serializers.CharField()
    value = serializers.CharField()


class ProductSerializer(serializers.Serializer):
    """Response projection of a product (management view)."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField()
    name = serializers.CharField()
    product_type = serializers.CharField()
    values = AttributeValueSerializer(many=True)
    metadata = serializers.DictField(child=serializers.CharField())
    is_published = serializers.BooleanField()
    # Present on the management list projection; absent (defaults to empty) on the
    # single-product responses that do not carry membership.
    categories = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class SetProductPublishedSerializer(serializers.Serializer):
    """Request body for changing a product's published flag."""

    is_published = serializers.BooleanField()


class StorefrontImageSerializer(serializers.Serializer):
    """A product's primary storefront image (promoted from one of its variants)."""

    url = serializers.CharField()
    alt_text = serializers.CharField(allow_blank=True)


class StorefrontProductSerializer(serializers.Serializer):
    """Public projection of a published product (no internal ``id``).

    ``from_price``/``currency``/``available`` are present only when the list was
    requested for a specific ``channel``; the amount is an exact string (never a
    float) and is null when the product has no price in that channel. ``image`` is
    the product's primary image, or null when it has none (the client then shows a
    placeholder).
    """

    code = serializers.CharField()
    name = serializers.CharField()
    product_type = serializers.CharField()
    values = AttributeValueSerializer(many=True)
    metadata = serializers.DictField(child=serializers.CharField())
    image = StorefrontImageSerializer(allow_null=True)
    from_price = serializers.CharField(required=False, allow_null=True)
    currency = serializers.CharField(required=False, allow_null=True)
    available = serializers.BooleanField(required=False)


class StorefrontProductPageSerializer(serializers.Serializer):
    """A page of storefront products: the count, the window, and the items."""

    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = StorefrontProductSerializer(many=True)


class StorefrontProductQuerySerializer(serializers.Serializer):
    """Query-string parameters for the storefront product list.

    Filters are optional; pagination bounds are enforced by the use case so an
    out-of-range page surfaces as a domain 400 (this layer only checks types).
    """

    search = serializers.CharField(required=False)
    category = serializers.CharField(required=False)
    collection = serializers.CharField(required=False)
    product_type = serializers.CharField(required=False)
    # When given, each result is enriched with its "from" price + availability
    # in this channel. A price range (below) also filters against this channel.
    channel = serializers.CharField(required=False)
    # Money bounds are exact decimals (never floats). They only take effect when a
    # channel is supplied, since price is per-channel.
    min_price = serializers.DecimalField(
        required=False, max_digits=18, decimal_places=4, min_value=0
    )
    max_price = serializers.DecimalField(
        required=False, max_digits=18, decimal_places=4, min_value=0
    )
    limit = serializers.IntegerField(required=False)
    offset = serializers.IntegerField(required=False)


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


class StorefrontVariantPriceSerializer(serializers.Serializer):
    """A variant's storefront price (amount as an exact string, currency from the channel)."""

    amount = serializers.CharField()
    currency = serializers.CharField()


class StorefrontVariantSerializer(serializers.Serializer):
    """A published product's variant projected for the storefront (no internal id).

    ``price`` is ``null`` when the variant has no base price in the requested channel.
    """

    sku = serializers.CharField()
    name = serializers.CharField()
    values = AttributeValueSerializer(many=True)
    media = VariantMediaSerializer(many=True)
    price = StorefrontVariantPriceSerializer(allow_null=True)


class StorefrontProductVariantsSerializer(serializers.Serializer):
    """Response projection of a published product's purchasable variants in a channel."""

    channel = serializers.CharField()
    variants = StorefrontVariantSerializer(many=True)


class StorefrontVariantsQuerySerializer(serializers.Serializer):
    """Query parameter selecting the channel a product's variants are priced in."""

    channel = serializers.CharField()


class StorefrontCategorySerializer(serializers.Serializer):
    """Public projection of a category for storefront filter choosers (no internal id)."""

    slug = serializers.CharField()
    name = serializers.CharField()
    parent = serializers.CharField(allow_null=True)


class StorefrontCollectionSerializer(serializers.Serializer):
    """Public projection of a collection for storefront filter choosers (no internal id)."""

    slug = serializers.CharField()
    name = serializers.CharField()


class StorefrontProductTypeSerializer(serializers.Serializer):
    """Public projection of a product type for storefront filter choosers."""

    code = serializers.CharField()
    name = serializers.CharField()


class CreateVariantSerializer(serializers.Serializer):
    """Request body for creating a variant (the parent product comes from the URL)."""

    sku = serializers.CharField()
    name = serializers.CharField()
    values = AttributeValueSerializer(many=True, required=False, default=list)
    media = VariantMediaSerializer(many=True, required=False, default=list)


class CategorySerializer(serializers.Serializer):
    """Response projection of a category (``parent`` is null for a root)."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField()
    name = serializers.CharField()
    parent = serializers.CharField(allow_null=True)


class CreateCategorySerializer(serializers.Serializer):
    """Request body for creating a category."""

    slug = serializers.CharField()
    name = serializers.CharField()
    parent = serializers.CharField(required=False, allow_null=True, default=None)


class ProductCategoriesSerializer(serializers.Serializer):
    """Response/request projection of a product's category membership (ordered slugs)."""

    categories = serializers.ListField(child=serializers.CharField())


class CollectionSerializer(serializers.Serializer):
    """Response projection of a collection (a curated grouping)."""

    id = serializers.IntegerField(read_only=True)
    slug = serializers.CharField()
    name = serializers.CharField()


class CreateCollectionSerializer(serializers.Serializer):
    """Request body for creating a collection."""

    slug = serializers.CharField()
    name = serializers.CharField()


class CollectionProductsSerializer(serializers.Serializer):
    """Response/request projection of a collection's product membership (ordered codes)."""

    products = serializers.ListField(child=serializers.CharField())


class RuleConditionSerializer(serializers.Serializer):
    """One condition of a rule-based collection's membership rule."""

    attribute = serializers.CharField()
    operator = serializers.CharField()
    value = serializers.CharField()


class CollectionRuleSerializer(serializers.Serializer):
    """Response/request projection of a collection's membership rule (ordered conditions)."""

    conditions = RuleConditionSerializer(many=True)


class CollectionRuleMembersSerializer(serializers.Serializer):
    """Response projection of the products a rule-based collection currently selects."""

    products = serializers.ListField(child=serializers.CharField())


class ChannelPriceInputSerializer(serializers.Serializer):
    """One channel price in a replace request (the currency is derived from the channel)."""

    channel = serializers.CharField()
    amount = serializers.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )


class SetVariantPricesSerializer(serializers.Serializer):
    """Request body for replacing a variant's per-channel base prices (empty clears)."""

    prices = ChannelPriceInputSerializer(many=True)


class ChannelPriceSerializer(serializers.Serializer):
    """One channel price in a response, with the currency derived from the channel."""

    channel = serializers.CharField()
    # Serialized as a string to preserve the exact Decimal (never a float).
    amount = serializers.CharField()
    currency = serializers.CharField()


class VariantPricesSerializer(serializers.Serializer):
    """Response projection of a variant's per-channel base prices."""

    prices = ChannelPriceSerializer(many=True)


class SetVariantStockSerializer(serializers.Serializer):
    """Request body for setting a variant's absolute on-hand stock quantity.

    The non-negative rule is the domain's (a negative value surfaces as a 400 from
    ``StockQuantity``); this only checks the field is present and an integer.
    """

    quantity = serializers.IntegerField()


class AdjustVariantStockSerializer(serializers.Serializer):
    """Request body for adjusting a variant's stock by a signed delta."""

    delta = serializers.IntegerField()


class VariantStockSerializer(serializers.Serializer):
    """Response projection of a variant's on-hand stock quantity."""

    quantity = serializers.IntegerField()


class ProductImportRequestSerializer(serializers.Serializer):
    """Request body for a bulk product import: a single uploaded CSV file."""

    file = serializers.FileField()


class ImportRowErrorSerializer(serializers.Serializer):
    """One row that failed import (``row_number`` 0 marks a whole-file failure)."""

    row_number = serializers.IntegerField()
    code = serializers.CharField(allow_blank=True)
    error = serializers.CharField()


class ProductImportResultSerializer(serializers.Serializer):
    """Result of a bulk import: the created count and any per-row errors.

    The import is all-or-nothing: with any errors nothing is created (``created`` is
    0); the same shape is returned on success (200) and failure (400).
    """

    created = serializers.IntegerField()
    errors = ImportRowErrorSerializer(many=True)
