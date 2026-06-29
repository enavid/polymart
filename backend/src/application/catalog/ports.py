"""Ports (interfaces) for the catalog use cases.

The application layer depends only on these abstractions. Concrete adapters
(Django ORM, in-memory fakes) live elsewhere and are injected at the composition
root, keeping the dependency rule pointing inward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.catalog.entities import (
    Attribute,
    Category,
    Collection,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.value_objects import (
    CategorySlug,
    ChannelPrice,
    ProductCode,
    RuleCondition,
    StockQuantity,
)


class AttributeRepository(ABC):
    """Persistence boundary for the Attribute aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``AttributeNotFoundError``, ``AttributeAlreadyExistsError``) so
    that callers never see infrastructure leaks.
    """

    @abstractmethod
    def add(self, attribute: Attribute) -> Attribute:
        """Persist a new attribute and return it with its assigned identity.

        Raises ``AttributeAlreadyExistsError`` if the code is already taken.
        """

    @abstractmethod
    def get_by_code(self, code: str) -> Attribute:
        """Return the attribute with this code or raise ``AttributeNotFoundError``."""

    @abstractmethod
    def exists_by_code(self, code: str) -> bool:
        """Return whether an attribute with this code already exists."""

    @abstractmethod
    def list_all(self) -> list[Attribute]:
        """Return every attribute, ordered by code for deterministic output."""


class ProductTypeRepository(ABC):
    """Persistence boundary for the ProductType aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``ProductTypeNotFoundError``, ``ProductTypeAlreadyExistsError``)
    so that callers never see infrastructure leaks.
    """

    @abstractmethod
    def add(self, product_type: ProductType) -> ProductType:
        """Persist a new product type and return it with its assigned identity.

        Raises ``ProductTypeAlreadyExistsError`` if the code is already taken.
        """

    @abstractmethod
    def get_by_code(self, code: str) -> ProductType:
        """Return the product type with this code or raise ``ProductTypeNotFoundError``."""

    @abstractmethod
    def exists_by_code(self, code: str) -> bool:
        """Return whether a product type with this code already exists."""

    @abstractmethod
    def list_all(self) -> list[ProductType]:
        """Return every product type, ordered by code for deterministic output."""


class ProductRepository(ABC):
    """Persistence boundary for the Product aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``ProductNotFoundError``, ``ProductAlreadyExistsError``) so that
    callers never see infrastructure leaks.
    """

    @abstractmethod
    def add(self, product: Product) -> Product:
        """Persist a new product and return it with its assigned identity.

        Raises ``ProductAlreadyExistsError`` if the code is already taken.
        """

    @abstractmethod
    def get_by_code(self, code: str) -> Product:
        """Return the product with this code or raise ``ProductNotFoundError``."""

    @abstractmethod
    def exists_by_code(self, code: str) -> bool:
        """Return whether a product with this code already exists."""

    @abstractmethod
    def list_all(self) -> list[Product]:
        """Return every product, ordered by code for deterministic output."""

    @abstractmethod
    def set_published(self, code: str, is_published: bool) -> Product:
        """Set a product's published flag and return the updated product.

        Raises ``ProductNotFoundError`` if the product does not exist.
        """


class VariantRepository(ABC):
    """Persistence boundary for the ProductVariant aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``VariantNotFoundError``, ``VariantAlreadyExistsError``,
    ``ProductNotFoundError`` for a missing parent) so callers never see
    infrastructure leaks.
    """

    @abstractmethod
    def add(self, variant: ProductVariant) -> ProductVariant:
        """Persist a new variant and return it with its assigned identity.

        Raises ``VariantAlreadyExistsError`` if the SKU is already taken, and
        ``ProductNotFoundError`` if the parent product does not exist.
        """

    @abstractmethod
    def get_by_sku(self, sku: str) -> ProductVariant:
        """Return the variant with this SKU or raise ``VariantNotFoundError``."""

    @abstractmethod
    def exists_by_sku(self, sku: str) -> bool:
        """Return whether a variant with this SKU already exists."""

    @abstractmethod
    def list_for_product(self, product_code: str) -> list[ProductVariant]:
        """Return the variants of one product, ordered by SKU for deterministic output."""


class CategoryRepository(ABC):
    """Persistence boundary for the Category aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``CategoryNotFoundError``, ``CategoryAlreadyExistsError``,
    ``ParentCategoryNotFoundError`` for a missing parent) so callers never see
    infrastructure leaks.
    """

    @abstractmethod
    def add(self, category: Category) -> Category:
        """Persist a new category and return it with its assigned identity.

        Raises ``CategoryAlreadyExistsError`` if the slug is already taken, and
        ``ParentCategoryNotFoundError`` if the referenced parent does not exist.
        """

    @abstractmethod
    def get_by_slug(self, slug: str) -> Category:
        """Return the category with this slug or raise ``CategoryNotFoundError``."""

    @abstractmethod
    def exists_by_slug(self, slug: str) -> bool:
        """Return whether a category with this slug already exists."""

    @abstractmethod
    def list_all(self) -> list[Category]:
        """Return every category, ordered by slug for deterministic output."""


class ProductCategoryRepository(ABC):
    """Persistence boundary for a product's category membership (a join table).

    Implementations MUST translate storage-specific failures into domain
    exceptions (``ProductNotFoundError`` for a missing product,
    ``UnknownCategoryError`` for a referenced category that does not exist) so
    callers never see infrastructure leaks.
    """

    @abstractmethod
    def replace(
        self, product_code: str, categories: Sequence[CategorySlug]
    ) -> tuple[CategorySlug, ...]:
        """Replace a product's whole category membership atomically.

        Returns the stored membership in assignment order. Raises
        ``ProductNotFoundError`` if the product does not exist and
        ``UnknownCategoryError`` if a referenced category does not exist (the whole
        replace then rolls back).
        """

    @abstractmethod
    def list_for_product(self, product_code: str) -> tuple[CategorySlug, ...]:
        """Return a product's categories in assignment order (empty if none)."""


class CollectionRepository(ABC):
    """Persistence boundary for the Collection aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``CollectionNotFoundError``, ``CollectionAlreadyExistsError``) so
    callers never see infrastructure leaks.
    """

    @abstractmethod
    def add(self, collection: Collection) -> Collection:
        """Persist a new collection and return it with its assigned identity.

        Raises ``CollectionAlreadyExistsError`` if the slug is already taken.
        """

    @abstractmethod
    def get_by_slug(self, slug: str) -> Collection:
        """Return the collection with this slug or raise ``CollectionNotFoundError``."""

    @abstractmethod
    def exists_by_slug(self, slug: str) -> bool:
        """Return whether a collection with this slug already exists."""

    @abstractmethod
    def list_all(self) -> list[Collection]:
        """Return every collection, ordered by slug for deterministic output."""


class CollectionProductRepository(ABC):
    """Persistence boundary for a collection's product membership (a join table).

    Implementations MUST translate storage-specific failures into domain
    exceptions (``CollectionNotFoundError`` for a missing collection,
    ``UnknownProductError`` for a referenced product that does not exist) so
    callers never see infrastructure leaks.
    """

    @abstractmethod
    def replace(
        self, collection_slug: str, products: Sequence[ProductCode]
    ) -> tuple[ProductCode, ...]:
        """Replace a collection's whole product membership atomically.

        Returns the stored membership in assignment order. Raises
        ``CollectionNotFoundError`` if the collection does not exist and
        ``UnknownProductError`` if a referenced product does not exist (the whole
        replace then rolls back).
        """

    @abstractmethod
    def list_for_collection(self, collection_slug: str) -> tuple[ProductCode, ...]:
        """Return a collection's products in assignment order (empty if none)."""


class CollectionRuleRepository(ABC):
    """Persistence boundary for a rule-based collection's membership rule.

    A rule is an ordered set of conditions belonging to a collection (a separate
    facet from the curated membership). Implementations MUST translate
    storage-specific failures into domain exceptions (``CollectionNotFoundError``
    for a missing collection, ``UnknownAttributeError`` for a referenced attribute
    that does not exist) so callers never see infrastructure leaks.
    """

    @abstractmethod
    def replace(
        self, collection_slug: str, conditions: Sequence[RuleCondition]
    ) -> tuple[RuleCondition, ...]:
        """Replace a collection's whole rule atomically.

        Returns the stored conditions in order. Raises ``CollectionNotFoundError``
        if the collection does not exist and ``UnknownAttributeError`` if a
        referenced attribute does not exist (the whole replace then rolls back).
        """

    @abstractmethod
    def list_for_collection(self, collection_slug: str) -> tuple[RuleCondition, ...]:
        """Return a collection's rule conditions in order (empty if no rule)."""


class VariantPriceRepository(ABC):
    """Persistence boundary for a variant's per-channel base prices.

    A variant's prices are a set keyed by channel (a separate facet from the
    variant's own attributes/media). Implementations MUST translate storage-specific
    failures into domain exceptions (``VariantNotFoundError`` for a missing variant)
    so callers never see infrastructure leaks.
    """

    @abstractmethod
    def replace(self, sku: str, prices: Sequence[ChannelPrice]) -> tuple[ChannelPrice, ...]:
        """Replace a variant's whole set of channel prices atomically.

        Returns the stored prices ordered by channel for deterministic output.
        Raises ``VariantNotFoundError`` if the variant does not exist (the whole
        replace then rolls back).
        """

    @abstractmethod
    def list_for_variant(self, sku: str) -> tuple[ChannelPrice, ...]:
        """Return a variant's channel prices, ordered by channel (empty if none)."""


class StockRepository(ABC):
    """Persistence boundary for a variant's on-hand stock quantity.

    A variant's stock is a single non-negative count (a separate facet from its
    attributes/media/prices). Implementations MUST translate storage-specific
    failures into domain exceptions (``VariantNotFoundError`` for a missing variant)
    so callers never see infrastructure leaks. ``adjust_quantity`` performs an
    atomic read-modify-write under a row lock so concurrent adjustments cannot lose
    an update or oversell.
    """

    @abstractmethod
    def get_quantity(self, sku: str) -> StockQuantity:
        """Return the variant's on-hand quantity (zero if it has no stock record)."""

    @abstractmethod
    def set_quantity(self, sku: str, quantity: StockQuantity) -> StockQuantity:
        """Set the variant's on-hand quantity to an absolute value and return it.

        Raises ``VariantNotFoundError`` if the variant does not exist.
        """

    @abstractmethod
    def adjust_quantity(self, sku: str, delta: int) -> StockQuantity:
        """Apply a signed delta atomically and return the new quantity.

        The read-modify-write is serialized with a row lock. Raises
        ``VariantNotFoundError`` if the variant does not exist and
        ``InsufficientStockError`` if the delta would drive the quantity below zero
        (the change is then not applied).
        """


@dataclass(frozen=True)
class ProductFilters:
    """The criteria a storefront product search is narrowed by (all AND-combined).

    Every field is optional; an unset field does not constrain the result.
    ``published_only`` is set by the read use case (never by the client) so the
    public surface can never be asked to include drafts.
    """

    search: str | None = None
    category: str | None = None
    collection: str | None = None
    product_type: str | None = None
    published_only: bool = True


@dataclass(frozen=True)
class ProductPage:
    """One page of a product search: the windowed items plus the full match count.

    ``total`` is the number of products matching the filters, independent of the
    page window, so the caller can render pagination controls.
    """

    items: tuple[Product, ...]
    total: int


class ProductQueryRepository(ABC):
    """Read-optimised boundary for storefront product browsing (a query side).

    Separate from the write-side ``ProductRepository`` because browsing is a
    fundamentally different access pattern (filtered, paged, published-gated) than
    managing a single aggregate. Implementations MUST translate storage-specific
    failures into domain exceptions (``ProductNotFoundError``) so callers never see
    infrastructure leaks.
    """

    @abstractmethod
    def search(self, *, filters: ProductFilters, limit: int, offset: int) -> ProductPage:
        """Return the products matching ``filters``, ordered by code, windowed by
        ``offset``/``limit``, together with the total match count."""

    @abstractmethod
    def get_published_by_code(self, code: str) -> Product:
        """Return the published product with this code.

        Raises ``ProductNotFoundError`` if no product with that code exists *or* it
        exists but is not published -- a draft must be indistinguishable from a
        missing product, so its existence is never leaked.
        """


@dataclass(frozen=True)
class ProductImportItem:
    """A validated product plus its category membership, ready to persist.

    The import use case validates rows (read-only) and hands the writer a batch of
    these; the writer owns only the atomic persistence, not the validation.
    """

    product: Product
    categories: tuple[CategorySlug, ...] = ()


class CatalogImportWriter(ABC):
    """Persistence boundary for a bulk product import (write side, all-or-nothing).

    Splitting this from ``ProductRepository`` keeps the single-aggregate writer free
    of batch concerns and lets the import own its own transaction boundary: the use
    case decides *what* to write (validated entities); the adapter decides *how*
    (one transaction spanning every product and its category links).
    """

    @abstractmethod
    def create_products(self, items: Sequence[ProductImportItem]) -> None:
        """Persist every item's product and category membership in one transaction.

        All-or-nothing: any failure rolls the whole batch back so a partial import
        is impossible. Raises a domain exception (e.g. ``ProductAlreadyExistsError``)
        if a persistence race is lost, so callers never see an infrastructure leak.
        """


class ChannelReader(ABC):
    """Read-only boundary onto the channel context for the catalog.

    Pricing is per-channel and the currency is the channel's, so the catalog must
    learn a channel's currency without depending on the channel domain. This narrow
    port exposes exactly that; the adapter bridges to the channel context.
    """

    @abstractmethod
    def currency_of(self, channel_slug: str) -> str | None:
        """Return the channel's ISO 4217 currency code, or ``None`` if it does not exist."""
