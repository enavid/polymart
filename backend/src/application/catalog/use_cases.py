"""Catalog use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the
domain, side effects (logging, audit) observable.

The catalog schema is white-label configuration: changing it reshapes every
storefront built on it, so each definition mutation emits a structured,
audit-friendly event naming the actor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    AttributeRepository,
    CategoryRepository,
    ProductCategoryRepository,
    ProductRepository,
    ProductTypeRepository,
    VariantRepository,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import (
    Attribute,
    Category,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    CategoryAlreadyExistsError,
    InvalidAttributeInputTypeError,
    ParentCategoryNotFoundError,
    ProductAlreadyExistsError,
    ProductTypeAlreadyExistsError,
    UnknownAttributeError,
    UnknownCategoryError,
    VariantAlreadyExistsError,
)
from src.domain.catalog.services import (
    normalize_attribute_values,
    reject_duplicate_categories,
)
from src.domain.catalog.value_objects import (
    AttributeChoice,
    AttributeCode,
    AttributeValue,
    CategorySlug,
    MediaAsset,
    ProductCode,
    ProductTypeCode,
    Sku,
)

logger = structlog.get_logger(__name__)

# Audit vocabulary for the catalog context. Namespaced ("<resource>.*") so the
# trail stays greppable by area.
_RESOURCE_ATTRIBUTE = "attribute"
_ACTION_ATTRIBUTE_CREATED = "attribute.created"
_RESOURCE_PRODUCT_TYPE = "product_type"
_ACTION_PRODUCT_TYPE_CREATED = "product_type.created"
_RESOURCE_PRODUCT = "product"
_ACTION_PRODUCT_CREATED = "product.created"
_RESOURCE_VARIANT = "variant"
_ACTION_VARIANT_CREATED = "variant.created"
_RESOURCE_CATEGORY = "category"
_ACTION_CATEGORY_CREATED = "category.created"
_ACTION_PRODUCT_CATEGORIES_CHANGED = "product.categories_changed"

# Membership is recorded in the audit trail as a deterministic, comma-joined slug
# string (AuditValue is a flat scalar, never a list).
_CATEGORY_JOIN = ","


def _join_categories(categories: tuple[CategorySlug, ...]) -> str:
    return _CATEGORY_JOIN.join(category.value for category in categories)


@dataclass(frozen=True)
class AttributeChoiceInput:
    """Raw choice input. Validated into an ``AttributeChoice`` by the domain."""

    value: str
    label: str


@dataclass(frozen=True)
class CreateAttributeCommand:
    """Input for creating an attribute. Raw strings are validated by the domain."""

    code: str
    name: str
    input_type: str
    required: bool = False
    choices: tuple[AttributeChoiceInput, ...] = field(default_factory=tuple)


def _to_input_type(raw: str) -> AttributeInputType:
    """Resolve a raw string to the enum, as a domain error if it is unknown."""
    try:
        return AttributeInputType(raw)
    except ValueError as exc:
        raise InvalidAttributeInputTypeError(raw) from exc


class CreateAttribute:
    """Register a new dynamic attribute definition."""

    def __init__(self, repository: AttributeRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(self, command: CreateAttributeCommand, *, actor: str | None = None) -> Attribute:
        # Build value objects first: invalid input fails fast, before any I/O.
        attribute = Attribute(
            code=AttributeCode(command.code),
            name=command.name,
            input_type=_to_input_type(command.input_type),
            required=command.required,
            choices=tuple(
                AttributeChoice(value=choice.value, label=choice.label)
                for choice in command.choices
            ),
        )
        code = attribute.code.value

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_code(code):
            logger.warning("attribute_create_rejected_duplicate", code=code, actor=actor)
            raise AttributeAlreadyExistsError(code)

        persisted = self._repository.add(attribute)
        logger.info(
            "attribute_created",
            attribute_id=persisted.id,
            code=code,
            input_type=persisted.input_type.value,
            required=persisted.required,
            choice_count=len(persisted.choices),
            actor=actor,
        )
        # Durable audit trail (creation has only "after" values).
        self._audit.record(
            action=_ACTION_ATTRIBUTE_CREATED,
            resource_type=_RESOURCE_ATTRIBUTE,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="code", after=code),
                FieldChange(field="input_type", after=persisted.input_type.value),
                FieldChange(field="required", after=persisted.required),
                FieldChange(field="choice_count", after=len(persisted.choices)),
            ),
        )
        return persisted


class GetAttribute:
    """Retrieve a single attribute by code."""

    def __init__(self, repository: AttributeRepository) -> None:
        self._repository = repository

    def execute(self, *, code: str) -> Attribute:
        attribute = self._repository.get_by_code(code)
        logger.debug("attribute_retrieved", code=code)
        return attribute


class ListAttributes:
    """List every attribute definition."""

    def __init__(self, repository: AttributeRepository) -> None:
        self._repository = repository

    def execute(self) -> list[Attribute]:
        attributes = self._repository.list_all()
        logger.debug("attributes_listed", count=len(attributes))
        return attributes


@dataclass(frozen=True)
class CreateProductTypeCommand:
    """Input for creating a product type. Raw strings are validated by the domain."""

    code: str
    name: str
    attributes: tuple[str, ...] = field(default_factory=tuple)
    variant_attributes: tuple[str, ...] = field(default_factory=tuple)


class CreateProductType:
    """Register a new product type that assigns a set of attributes."""

    def __init__(
        self,
        repository: ProductTypeRepository,
        attributes: AttributeRepository,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._attributes = attributes
        self._audit = audit

    def execute(
        self, command: CreateProductTypeCommand, *, actor: str | None = None
    ) -> ProductType:
        # Build value objects first: invalid input (codes, name, duplicate refs
        # within or across the two attribute levels) fails fast, before any I/O.
        product_type = ProductType(
            code=ProductTypeCode(command.code),
            name=command.name,
            attributes=tuple(AttributeCode(code) for code in command.attributes),
            variant_attributes=tuple(AttributeCode(code) for code in command.variant_attributes),
        )
        code = product_type.code.value

        # Both levels reference real attributes; uniqueness across them is already
        # enforced by the entity.
        self._reject_unknown_attributes(
            (*product_type.attributes, *product_type.variant_attributes), actor=actor
        )

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_code(code):
            logger.warning("product_type_create_rejected_duplicate", code=code, actor=actor)
            raise ProductTypeAlreadyExistsError(code)

        persisted = self._repository.add(product_type)
        logger.info(
            "product_type_created",
            product_type_id=persisted.id,
            code=code,
            attribute_count=len(persisted.attributes),
            variant_attribute_count=len(persisted.variant_attributes),
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_PRODUCT_TYPE_CREATED,
            resource_type=_RESOURCE_PRODUCT_TYPE,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="code", after=code),
                FieldChange(field="attribute_count", after=len(persisted.attributes)),
                FieldChange(
                    field="variant_attribute_count",
                    after=len(persisted.variant_attributes),
                ),
            ),
        )
        return persisted

    def _reject_unknown_attributes(
        self, attributes: tuple[AttributeCode, ...], *, actor: str | None
    ) -> None:
        for attribute in attributes:
            if not self._attributes.exists_by_code(attribute.value):
                logger.warning(
                    "product_type_create_rejected_unknown_attribute",
                    attribute=attribute.value,
                    actor=actor,
                )
                raise UnknownAttributeError(attribute.value)


class GetProductType:
    """Retrieve a single product type by code."""

    def __init__(self, repository: ProductTypeRepository) -> None:
        self._repository = repository

    def execute(self, *, code: str) -> ProductType:
        product_type = self._repository.get_by_code(code)
        logger.debug("product_type_retrieved", code=code)
        return product_type


class ListProductTypes:
    """List every product type."""

    def __init__(self, repository: ProductTypeRepository) -> None:
        self._repository = repository

    def execute(self) -> list[ProductType]:
        product_types = self._repository.list_all()
        logger.debug("product_types_listed", count=len(product_types))
        return product_types


@dataclass(frozen=True)
class AttributeValueInput:
    """Raw value input for one attribute. Validated/normalized by the domain."""

    attribute: str
    value: str


@dataclass(frozen=True)
class CreateProductCommand:
    """Input for creating a product. Raw strings are validated by the domain."""

    code: str
    name: str
    product_type: str
    values: tuple[AttributeValueInput, ...] = field(default_factory=tuple)
    metadata: Mapping[str, str] = field(default_factory=dict)


class CreateProduct:
    """Create a product whose attribute values conform to its product type.

    The product type and the attribute definitions live in other aggregates, so
    this use case loads them and delegates the conformance rule to the domain
    service; it owns only the orchestration (fetch, validate, persist, observe).
    """

    def __init__(
        self,
        repository: ProductRepository,
        product_types: ProductTypeRepository,
        attributes: AttributeRepository,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._product_types = product_types
        self._attributes = attributes
        self._audit = audit

    def execute(self, command: CreateProductCommand, *, actor: str | None = None) -> Product:
        # Build value objects first: malformed code/name/metadata or a duplicate
        # attribute value fails fast, before any I/O.
        product = Product(
            code=ProductCode(command.code),
            name=command.name,
            product_type=ProductTypeCode(command.product_type),
            values=tuple(
                AttributeValue(attribute=AttributeCode(item.attribute), value=item.value)
                for item in command.values
            ),
            metadata=command.metadata,
        )
        code = product.code.value

        # Resolve the product type and its attribute definitions (in declared
        # order), then let the domain service decide value conformance.
        product_type = self._product_types.get_by_code(product.product_type.value)
        definitions = [
            self._attributes.get_by_code(attribute.value) for attribute in product_type.attributes
        ]
        product.values = normalize_attribute_values(definitions, product.values)

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_code(code):
            logger.warning("product_create_rejected_duplicate", code=code, actor=actor)
            raise ProductAlreadyExistsError(code)

        persisted = self._repository.add(product)
        logger.info(
            "product_created",
            product_id=persisted.id,
            code=code,
            product_type=product_type.code.value,
            value_count=len(persisted.values),
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_PRODUCT_CREATED,
            resource_type=_RESOURCE_PRODUCT,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="code", after=code),
                FieldChange(field="product_type", after=product_type.code.value),
                FieldChange(field="value_count", after=len(persisted.values)),
            ),
        )
        return persisted


class GetProduct:
    """Retrieve a single product by code."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def execute(self, *, code: str) -> Product:
        product = self._repository.get_by_code(code)
        logger.debug("product_retrieved", code=code)
        return product


class ListProducts:
    """List every product."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def execute(self) -> list[Product]:
        products = self._repository.list_all()
        logger.debug("products_listed", count=len(products))
        return products


@dataclass(frozen=True)
class MediaInput:
    """Raw media input for a variant. Validated into a ``MediaAsset`` by the domain."""

    url: str
    alt_text: str = ""


@dataclass(frozen=True)
class CreateVariantCommand:
    """Input for creating a variant. Raw strings are validated by the domain."""

    product: str
    sku: str
    name: str
    values: tuple[AttributeValueInput, ...] = field(default_factory=tuple)
    media: tuple[MediaInput, ...] = field(default_factory=tuple)


class CreateVariant:
    """Create a sellable variant under an existing product.

    The parent product, its product type, and the attribute definitions all live
    in other aggregates, so this use case loads them, delegates option-value
    conformance to the domain service (against the type's *variant* attributes),
    then persists. It owns only the orchestration (build, verify, conform,
    persist, observe).
    """

    def __init__(
        self,
        repository: VariantRepository,
        products: ProductRepository,
        product_types: ProductTypeRepository,
        attributes: AttributeRepository,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._products = products
        self._product_types = product_types
        self._attributes = attributes
        self._audit = audit

    def execute(self, command: CreateVariantCommand, *, actor: str | None = None) -> ProductVariant:
        # Build value objects first: a malformed SKU, blank name, or duplicate
        # value fails fast, before any I/O.
        variant = ProductVariant(
            product=ProductCode(command.product),
            sku=Sku(command.sku),
            name=command.name,
            values=tuple(
                AttributeValue(attribute=AttributeCode(item.attribute), value=item.value)
                for item in command.values
            ),
            media=tuple(MediaAsset(url=item.url, alt_text=item.alt_text) for item in command.media),
        )
        product_code = variant.product.value
        sku = variant.sku.value

        # The parent must exist; raise ProductNotFoundError otherwise (a 404 at the
        # transport edge). The repository defends the concurrent-deletion race too.
        product = self._products.get_by_code(product_code)

        # Conform the option values to the product type's *variant* attributes,
        # reusing the same domain service the product head uses for its values.
        product_type = self._product_types.get_by_code(product.product_type.value)
        definitions = [
            self._attributes.get_by_code(attribute.value)
            for attribute in product_type.variant_attributes
        ]
        variant.values = normalize_attribute_values(definitions, variant.values)

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_sku(sku):
            logger.warning("variant_create_rejected_duplicate", sku=sku, actor=actor)
            raise VariantAlreadyExistsError(sku)

        persisted = self._repository.add(variant)
        logger.info(
            "variant_created",
            variant_id=persisted.id,
            sku=sku,
            product=product_code,
            value_count=len(persisted.values),
            media_count=len(persisted.media),
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_VARIANT_CREATED,
            resource_type=_RESOURCE_VARIANT,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="sku", after=sku),
                FieldChange(field="product", after=product_code),
                FieldChange(field="value_count", after=len(persisted.values)),
                FieldChange(field="media_count", after=len(persisted.media)),
            ),
        )
        return persisted


class GetVariant:
    """Retrieve a single variant by SKU."""

    def __init__(self, repository: VariantRepository) -> None:
        self._repository = repository

    def execute(self, *, sku: str) -> ProductVariant:
        variant = self._repository.get_by_sku(sku)
        logger.debug("variant_retrieved", sku=sku)
        return variant


class ListProductVariants:
    """List the variants of one product (404 if the product does not exist)."""

    def __init__(self, repository: VariantRepository, products: ProductRepository) -> None:
        self._repository = repository
        self._products = products

    def execute(self, *, product_code: str) -> list[ProductVariant]:
        # Confirm the parent exists so an unknown product is a 404, not an empty list.
        self._products.get_by_code(product_code)
        variants = self._repository.list_for_product(product_code)
        logger.debug("product_variants_listed", product=product_code, count=len(variants))
        return variants


@dataclass(frozen=True)
class CreateCategoryCommand:
    """Input for creating a category. Raw strings are validated by the domain."""

    slug: str
    name: str
    parent: str | None = None


class CreateCategory:
    """Create a category, optionally nested under an existing parent.

    The entity owns the structural rules (name, no self-parenting); this use case
    owns the orchestration: confirm the referenced parent exists (a cross-aggregate
    fact the entity cannot reach), reject a duplicate slug, persist, and observe.
    On creation the new slug is brand new, so it cannot yet be an ancestor of
    anything -- no cycle is possible beyond self-parenting, which the entity already
    forbids. Re-parenting (and the cycle check it needs) is a later slice.
    """

    def __init__(self, repository: CategoryRepository, audit: AuditRecorder) -> None:
        self._repository = repository
        self._audit = audit

    def execute(self, command: CreateCategoryCommand, *, actor: str | None = None) -> Category:
        # Build value objects first: a malformed slug, blank name, or self-parenting
        # fails fast, before any I/O.
        category = Category(
            slug=CategorySlug(command.slug),
            name=command.name,
            parent=CategorySlug(command.parent) if command.parent is not None else None,
        )
        slug = category.slug.value

        # A referenced parent must exist; the repository defends the concurrent-
        # deletion race too.
        if category.parent is not None and not self._repository.exists_by_slug(
            category.parent.value
        ):
            logger.warning(
                "category_create_rejected_unknown_parent",
                parent=category.parent.value,
                actor=actor,
            )
            raise ParentCategoryNotFoundError(category.parent.value)

        # Pre-check for a clean error; the repository remains the source of truth
        # and will still raise on a concurrent insert.
        if self._repository.exists_by_slug(slug):
            logger.warning("category_create_rejected_duplicate", slug=slug, actor=actor)
            raise CategoryAlreadyExistsError(slug)

        persisted = self._repository.add(category)
        parent_slug = persisted.parent.value if persisted.parent is not None else None
        logger.info(
            "category_created",
            category_id=persisted.id,
            slug=slug,
            parent=parent_slug,
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_CATEGORY_CREATED,
            resource_type=_RESOURCE_CATEGORY,
            resource_id=str(persisted.id),
            actor=actor,
            changes=(
                FieldChange(field="slug", after=slug),
                FieldChange(field="parent", after=parent_slug),
            ),
        )
        return persisted


class GetCategory:
    """Retrieve a single category by slug."""

    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    def execute(self, *, slug: str) -> Category:
        category = self._repository.get_by_slug(slug)
        logger.debug("category_retrieved", slug=slug)
        return category


class ListCategories:
    """List every category."""

    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    def execute(self) -> list[Category]:
        categories = self._repository.list_all()
        logger.debug("categories_listed", count=len(categories))
        return categories


@dataclass(frozen=True)
class SetProductCategoriesCommand:
    """Input for replacing a product's category membership (raw slug strings)."""

    product: str
    categories: tuple[str, ...] = field(default_factory=tuple)


class SetProductCategories:
    """Replace a product's whole category membership (an idempotent set operation).

    The product, the categories, and the join all live in different aggregates, so
    this use case loads/validates them and delegates the replace to the repository
    (which performs it atomically). It owns the orchestration only: build, verify
    the product and every referenced category exist, reject duplicates, replace,
    and record a before/after audit entry.
    """

    def __init__(
        self,
        repository: ProductCategoryRepository,
        products: ProductRepository,
        categories: CategoryRepository,
        audit: AuditRecorder,
    ) -> None:
        self._repository = repository
        self._products = products
        self._categories = categories
        self._audit = audit

    def execute(
        self, command: SetProductCategoriesCommand, *, actor: str | None = None
    ) -> tuple[CategorySlug, ...]:
        # Build value objects first: a malformed or duplicated slug fails fast,
        # before any I/O.
        requested = reject_duplicate_categories(
            tuple(CategorySlug(slug) for slug in command.categories)
        )
        product_code = command.product

        # The product must exist (a 404 at the edge); its id anchors the audit entry.
        product = self._products.get_by_code(product_code)
        # Every referenced category must exist (a 400 at the edge); the repository
        # defends the concurrent-deletion race too.
        self._reject_unknown_categories(requested, actor=actor)

        before = self._repository.list_for_product(product_code)
        persisted = self._repository.replace(product_code, requested)
        logger.info(
            "product_categories_set",
            product_id=product.id,
            product=product_code,
            count=len(persisted),
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_PRODUCT_CATEGORIES_CHANGED,
            resource_type=_RESOURCE_PRODUCT,
            resource_id=str(product.id),
            actor=actor,
            changes=(
                FieldChange(
                    field="categories",
                    before=_join_categories(before),
                    after=_join_categories(persisted),
                ),
            ),
        )
        return persisted

    def _reject_unknown_categories(
        self, categories: tuple[CategorySlug, ...], *, actor: str | None
    ) -> None:
        for category in categories:
            if not self._categories.exists_by_slug(category.value):
                logger.warning(
                    "product_categories_rejected_unknown_category",
                    category=category.value,
                    actor=actor,
                )
                raise UnknownCategoryError(category.value)


class GetProductCategories:
    """List a product's categories (404 if the product does not exist)."""

    def __init__(self, repository: ProductCategoryRepository, products: ProductRepository) -> None:
        self._repository = repository
        self._products = products

    def execute(self, *, product_code: str) -> tuple[CategorySlug, ...]:
        # Confirm the product exists so an unknown product is a 404, not an empty set.
        self._products.get_by_code(product_code)
        categories = self._repository.list_for_product(product_code)
        logger.debug("product_categories_listed", product=product_code, count=len(categories))
        return categories
