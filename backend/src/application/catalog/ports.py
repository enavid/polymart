"""Ports (interfaces) for the catalog use cases.

The application layer depends only on these abstractions. Concrete adapters
(Django ORM, in-memory fakes) live elsewhere and are injected at the composition
root, keeping the dependency rule pointing inward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.catalog.entities import Attribute, Product, ProductType


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
