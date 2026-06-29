"""Domain exceptions for the catalog context.

Pure-Python exceptions with no framework coupling. The interface layer translates
them into transport-level responses (HTTP codes).
"""

from __future__ import annotations


class CatalogError(Exception):
    """Base class for every catalog domain error."""


class InvalidAttributeCodeError(CatalogError):
    """Raised when an attribute code is empty, too long, or not a slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid attribute code: {value!r}")
        self.value = value


class InvalidAttributeNameError(CatalogError):
    """Raised when an attribute display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid attribute name: {value!r}")
        self.value = value


class InvalidAttributeInputTypeError(CatalogError):
    """Raised when a raw input-type string matches no known attribute type."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid attribute input type: {value!r}")
        self.value = value


class InvalidAttributeChoiceError(CatalogError):
    """Raised when a choice's value or label is malformed."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid attribute choice: {detail}")
        self.detail = detail


class AttributeChoicesRequiredError(CatalogError):
    """Raised when a choice-type attribute is created without any choices."""

    def __init__(self, input_type: str) -> None:
        super().__init__(f"input type {input_type!r} requires at least one choice")
        self.input_type = input_type


class AttributeChoicesNotAllowedError(CatalogError):
    """Raised when a non-choice attribute is given choices it cannot use."""

    def __init__(self, input_type: str) -> None:
        super().__init__(f"input type {input_type!r} does not accept choices")
        self.input_type = input_type


class DuplicateAttributeChoiceError(CatalogError):
    """Raised when two choices share the same value within one attribute."""

    def __init__(self, value: str) -> None:
        super().__init__(f"duplicate attribute choice value: {value!r}")
        self.value = value


class InvalidProductTypeCodeError(CatalogError):
    """Raised when a product-type code is empty, too long, or not a slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid product type code: {value!r}")
        self.value = value


class InvalidProductTypeNameError(CatalogError):
    """Raised when a product-type display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid product type name: {value!r}")
        self.value = value


class DuplicateAttributeAssignmentError(CatalogError):
    """Raised when a product type references the same attribute more than once."""

    def __init__(self, code: str) -> None:
        super().__init__(f"duplicate attribute assignment: {code!r}")
        self.code = code


class UnknownAttributeError(CatalogError):
    """Raised when a product type references an attribute that does not exist."""

    def __init__(self, code: str) -> None:
        super().__init__(f"unknown attribute: {code!r}")
        self.code = code


class AttributeNotFoundError(CatalogError):
    """Raised when an attribute cannot be located by its code."""

    def __init__(self, code: str) -> None:
        super().__init__(f"attribute not found: {code!r}")
        self.code = code


class AttributeAlreadyExistsError(CatalogError):
    """Raised when creating an attribute whose code is already taken."""

    def __init__(self, code: str) -> None:
        super().__init__(f"attribute already exists: {code!r}")
        self.code = code


class ProductTypeNotFoundError(CatalogError):
    """Raised when a product type cannot be located by its code."""

    def __init__(self, code: str) -> None:
        super().__init__(f"product type not found: {code!r}")
        self.code = code


class ProductTypeAlreadyExistsError(CatalogError):
    """Raised when creating a product type whose code is already taken."""

    def __init__(self, code: str) -> None:
        super().__init__(f"product type already exists: {code!r}")
        self.code = code


class InvalidProductCodeError(CatalogError):
    """Raised when a product code is empty, too long, or not a slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid product code: {value!r}")
        self.value = value


class InvalidProductNameError(CatalogError):
    """Raised when a product display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid product name: {value!r}")
        self.value = value


class InvalidProductMetadataError(CatalogError):
    """Raised when a product metadata key or value is blank or too long."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid product metadata: {detail}")
        self.detail = detail


class DuplicateAttributeValueError(CatalogError):
    """Raised when a product supplies more than one value for the same attribute."""

    def __init__(self, code: str) -> None:
        super().__init__(f"duplicate attribute value: {code!r}")
        self.code = code


class UnassignedAttributeError(CatalogError):
    """Raised when a product values an attribute its product type does not assign."""

    def __init__(self, code: str) -> None:
        super().__init__(f"attribute not assigned to product type: {code!r}")
        self.code = code


class MissingRequiredAttributeError(CatalogError):
    """Raised when a product omits a value for a required attribute of its type."""

    def __init__(self, code: str) -> None:
        super().__init__(f"missing required attribute value: {code!r}")
        self.code = code


class InvalidAttributeValueError(CatalogError):
    """Raised when a value does not conform to its attribute's input type."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"invalid value for attribute {code!r}: {detail}")
        self.code = code
        self.detail = detail


class ProductNotFoundError(CatalogError):
    """Raised when a product cannot be located by its code."""

    def __init__(self, code: str) -> None:
        super().__init__(f"product not found: {code!r}")
        self.code = code


class ProductAlreadyExistsError(CatalogError):
    """Raised when creating a product whose code is already taken."""

    def __init__(self, code: str) -> None:
        super().__init__(f"product already exists: {code!r}")
        self.code = code


class InvalidSkuError(CatalogError):
    """Raised when a SKU is empty, too long, or not a stock-keeping code."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid sku: {value!r}")
        self.value = value


class InvalidVariantNameError(CatalogError):
    """Raised when a variant display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid variant name: {value!r}")
        self.value = value


class VariantNotFoundError(CatalogError):
    """Raised when a variant cannot be located by its SKU."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"variant not found: {sku!r}")
        self.sku = sku


class VariantAlreadyExistsError(CatalogError):
    """Raised when creating a variant whose SKU is already taken."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"variant already exists: {sku!r}")
        self.sku = sku


class InvalidMediaAssetError(CatalogError):
    """Raised when a media asset's URL or alt text is malformed."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid media asset: {detail}")
        self.detail = detail


class DuplicateMediaAssetError(CatalogError):
    """Raised when a variant lists the same media URL more than once."""

    def __init__(self, url: str) -> None:
        super().__init__(f"duplicate media asset url: {url!r}")
        self.url = url


class InvalidCategorySlugError(CatalogError):
    """Raised when a category slug is empty, too long, or not a slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid category slug: {value!r}")
        self.value = value


class InvalidCategoryNameError(CatalogError):
    """Raised when a category display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid category name: {value!r}")
        self.value = value


class SelfParentingCategoryError(CatalogError):
    """Raised when a category is given itself as its parent."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"category cannot be its own parent: {slug!r}")
        self.slug = slug


class CategoryNotFoundError(CatalogError):
    """Raised when a category cannot be located by its slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"category not found: {slug!r}")
        self.slug = slug


class CategoryAlreadyExistsError(CatalogError):
    """Raised when creating a category whose slug is already taken."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"category already exists: {slug!r}")
        self.slug = slug


class ParentCategoryNotFoundError(CatalogError):
    """Raised when a category references a parent that does not exist."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"parent category not found: {slug!r}")
        self.slug = slug


class DuplicateCategoryAssignmentError(CatalogError):
    """Raised when a product is assigned the same category more than once."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"duplicate category assignment: {slug!r}")
        self.slug = slug


class UnknownCategoryError(CatalogError):
    """Raised when a product is assigned a category that does not exist."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"unknown category: {slug!r}")
        self.slug = slug


class InvalidCollectionSlugError(CatalogError):
    """Raised when a collection slug is empty, too long, or not a slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid collection slug: {value!r}")
        self.value = value


class InvalidCollectionNameError(CatalogError):
    """Raised when a collection display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid collection name: {value!r}")
        self.value = value


class CollectionNotFoundError(CatalogError):
    """Raised when a collection cannot be located by its slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"collection not found: {slug!r}")
        self.slug = slug


class CollectionAlreadyExistsError(CatalogError):
    """Raised when creating a collection whose slug is already taken."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"collection already exists: {slug!r}")
        self.slug = slug


class DuplicateProductMembershipError(CatalogError):
    """Raised when a collection lists the same product more than once."""

    def __init__(self, code: str) -> None:
        super().__init__(f"duplicate product membership: {code!r}")
        self.code = code


class UnknownProductError(CatalogError):
    """Raised when a collection references a product that does not exist."""

    def __init__(self, code: str) -> None:
        super().__init__(f"unknown product: {code!r}")
        self.code = code


class InvalidRuleConditionError(CatalogError):
    """Raised when a rule-based collection condition's value is malformed."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid rule condition: {detail}")
        self.detail = detail


class InvalidRuleOperatorError(CatalogError):
    """Raised when a raw operator string matches no known rule operator."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid rule operator: {value!r}")
        self.value = value


class DuplicateRuleConditionError(CatalogError):
    """Raised when a rule lists the same (attribute, operator, value) more than once."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"duplicate rule condition: {detail}")
        self.detail = detail


class InvalidMoneyError(CatalogError):
    """Raised when a money amount or currency is malformed.

    Covers a non-Decimal or non-finite amount, a non-positive base price, an
    amount that exceeds the stored precision/scale, or a currency that is not a
    three-letter alpha code.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid money: {detail}")
        self.detail = detail


class InvalidChannelReferenceError(CatalogError):
    """Raised when a price references a channel with a blank or overlong slug."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid channel reference: {value!r}")
        self.value = value


class UnknownChannelError(CatalogError):
    """Raised when a price references a channel that does not exist."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"unknown channel: {slug!r}")
        self.slug = slug


class DuplicateChannelPriceError(CatalogError):
    """Raised when a variant is given more than one price for the same channel."""

    def __init__(self, channel: str) -> None:
        super().__init__(f"duplicate channel price: {channel!r}")
        self.channel = channel
