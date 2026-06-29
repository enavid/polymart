"""Ports (interfaces) for the catalog use cases.

The application layer depends only on these abstractions. Concrete adapters
(Django ORM, in-memory fakes) live elsewhere and are injected at the composition
root, keeping the dependency rule pointing inward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.catalog.entities import (
    Attribute,
    Category,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.value_objects import CategorySlug


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
