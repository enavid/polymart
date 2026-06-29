"""The Attribute entity: a reusable, typed property definition.

An attribute is the unit of the platform's flexible, white-label data model: it
declares a named, typed property (roast level, origin, weight, ...) that product
types later compose. The rules that make a definition coherent -- a name, and
choices that match the input type -- live here, in pure Python.

No Django, no DRF, no ORM.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeChoicesNotAllowedError,
    AttributeChoicesRequiredError,
    DuplicateAttributeAssignmentError,
    DuplicateAttributeChoiceError,
    DuplicateAttributeValueError,
    DuplicateMediaAssetError,
    InvalidAttributeNameError,
    InvalidCategoryNameError,
    InvalidCollectionNameError,
    InvalidProductMetadataError,
    InvalidProductNameError,
    InvalidProductTypeNameError,
    InvalidVariantNameError,
    SelfParentingCategoryError,
)
from src.domain.catalog.value_objects import (
    AttributeChoice,
    AttributeCode,
    AttributeValue,
    CategorySlug,
    CollectionSlug,
    MediaAsset,
    ProductCode,
    ProductTypeCode,
    Sku,
)

_NAME_MAX_LENGTH = 255
_METADATA_KEY_MAX_LENGTH = 64
_METADATA_VALUE_MAX_LENGTH = 1024


@dataclass
class Attribute:
    """A dynamic attribute definition.

    Identity is the database ``id`` once persisted, but the ``code`` is the stable
    business key used everywhere in the API.
    """

    code: AttributeCode
    name: str
    input_type: AttributeInputType
    required: bool = False
    choices: tuple[AttributeChoice, ...] = ()
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.choices = self._validated_choices(self.choices)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidAttributeNameError(raw)
        return name

    def _validated_choices(
        self, choices: tuple[AttributeChoice, ...]
    ) -> tuple[AttributeChoice, ...]:
        choices = tuple(choices)
        if self.input_type.is_choice_type:
            if not choices:
                raise AttributeChoicesRequiredError(self.input_type.value)
        elif choices:
            raise AttributeChoicesNotAllowedError(self.input_type.value)
        self._reject_duplicate_values(choices)
        return choices

    @staticmethod
    def _reject_duplicate_values(choices: tuple[AttributeChoice, ...]) -> None:
        seen: set[str] = set()
        for choice in choices:
            if choice.value in seen:
                raise DuplicateAttributeChoiceError(choice.value)
            seen.add(choice.value)


@dataclass
class ProductType:
    """A named template that assigns attributes to its products.

    The product type references attributes by code (it does not own them) in a
    stable display order, split across two levels: ``attributes`` are
    product-level (shared by every variant) and ``variant_attributes`` are the
    options that distinguish one variant from another (size, grind). A single
    attribute is assigned at most once *across both levels* -- being product- and
    variant-level at the same time would make a variant's value ambiguous.

    Whether each referenced attribute actually exists is an application-layer
    concern (validated against the attribute repository), since the entity cannot
    reach persistence.
    """

    code: ProductTypeCode
    name: str
    attributes: tuple[AttributeCode, ...] = ()
    variant_attributes: tuple[AttributeCode, ...] = ()
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.attributes = tuple(self.attributes)
        self.variant_attributes = tuple(self.variant_attributes)
        self._reject_duplicate_assignments()

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidProductTypeNameError(raw)
        return name

    def _reject_duplicate_assignments(self) -> None:
        # Uniqueness spans both levels: no attribute may repeat within a level or
        # appear on both, so a variant value always maps to exactly one definition.
        seen: set[str] = set()
        for attribute in (*self.attributes, *self.variant_attributes):
            if attribute.value in seen:
                raise DuplicateAttributeAssignmentError(attribute.value)
            seen.add(attribute.value)


@dataclass
class Product:
    """A sellable item built on a product type, carrying its attribute values.

    The product references its product type by code and supplies a value for some
    or all of that type's attributes. This entity owns only *structural* rules: a
    name, at most one value per attribute, and well-formed metadata. Whether each
    value conforms to its attribute's input type (and whether required attributes
    are present) is a cross-aggregate rule decided by the conformance domain
    service, which has the attribute definitions the entity cannot reach.

    ``metadata`` is free-form, string-keyed, string-valued extension data (mirroring
    Saleor's metadata) -- never a place for money, which is modelled with Decimal in
    the pricing slice.
    """

    code: ProductCode
    name: str
    product_type: ProductTypeCode
    values: tuple[AttributeValue, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.values = self._validated_values(self.values)
        self.metadata = self._validated_metadata(self.metadata)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidProductNameError(raw)
        return name

    @staticmethod
    def _validated_values(
        values: tuple[AttributeValue, ...],
    ) -> tuple[AttributeValue, ...]:
        values = tuple(values)
        seen: set[str] = set()
        for value in values:
            code = value.attribute.value
            if code in seen:
                raise DuplicateAttributeValueError(code)
            seen.add(code)
        return values

    @staticmethod
    def _validated_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        for key, value in metadata.items():
            stripped_key = key.strip()
            if not stripped_key or len(stripped_key) > _METADATA_KEY_MAX_LENGTH:
                raise InvalidProductMetadataError(f"key {key!r}")
            if len(value) > _METADATA_VALUE_MAX_LENGTH:
                raise InvalidProductMetadataError(f"value for key {stripped_key!r}")
            validated[stripped_key] = value
        return validated


@dataclass
class ProductVariant:
    """A sellable instance of a product, identified by a unique SKU.

    A variant references its parent product by code (it does not own it), carries
    its own stock-keeping identity, and supplies values for the *option*
    (variant-level) attributes of its product type. Whether the parent product
    exists, and whether each value conforms to a declared variant attribute, are
    application-layer concerns (the latter delegated to the conformance domain
    service). This entity owns only structural rules: a non-blank, bounded display
    name and at most one value per attribute.
    """

    product: ProductCode
    sku: Sku
    name: str
    values: tuple[AttributeValue, ...] = ()
    media: tuple[MediaAsset, ...] = ()
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self.values = self._validated_values(self.values)
        self.media = self._validated_media(self.media)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidVariantNameError(raw)
        return name

    @staticmethod
    def _validated_values(
        values: tuple[AttributeValue, ...],
    ) -> tuple[AttributeValue, ...]:
        values = tuple(values)
        seen: set[str] = set()
        for value in values:
            code = value.attribute.value
            if code in seen:
                raise DuplicateAttributeValueError(code)
            seen.add(code)
        return values

    @staticmethod
    def _validated_media(media: tuple[MediaAsset, ...]) -> tuple[MediaAsset, ...]:
        media = tuple(media)
        seen: set[str] = set()
        for asset in media:
            if asset.url in seen:
                raise DuplicateMediaAssetError(asset.url)
            seen.add(asset.url)
        return media


@dataclass
class Category:
    """A node in the hierarchical catalog taxonomy.

    A category groups products under a stable slug and, optionally, points at a
    parent category by slug -- ``None`` marks a root. This entity owns only
    *structural* rules: a non-blank, bounded display name, and the rule that a
    category is never its own parent. Whether the parent actually exists, and
    whether re-parenting would form a cycle, are tree-spanning concerns the entity
    cannot reach; they are decided in the application layer against the repository.
    """

    slug: CategorySlug
    name: str
    parent: CategorySlug | None = None
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)
        self._reject_self_parenting()

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidCategoryNameError(raw)
        return name

    def _reject_self_parenting(self) -> None:
        if self.parent is not None and self.parent == self.slug:
            raise SelfParentingCategoryError(self.slug.value)


@dataclass
class Collection:
    """A curated grouping of products, identified by a stable slug.

    Unlike a category, a collection is not a taxonomy node: it is a flat
    merchandising grouping (``Featured``, ``Summer Sale``) whose membership is
    hand-picked. This entity owns only *structural* rules: a non-blank, bounded
    display name. Which products belong to it is a separate, membership concern
    decided in the application layer.
    """

    slug: CollectionSlug
    name: str
    id: int | None = field(default=None)

    def __post_init__(self) -> None:
        self.name = self._validated_name(self.name)

    @staticmethod
    def _validated_name(raw: str) -> str:
        name = raw.strip()
        if not name or len(name) > _NAME_MAX_LENGTH:
            raise InvalidCollectionNameError(raw)
        return name
