"""Django ORM implementation of the catalog repository ports."""

from __future__ import annotations

import structlog
from django.db import IntegrityError, transaction

from src.application.catalog.ports import AttributeRepository, ProductTypeRepository
from src.domain.catalog.entities import Attribute, ProductType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
    UnknownAttributeError,
)
from src.infrastructure.catalog.mappers import (
    apply_product_type_scalar_fields,
    apply_scalar_fields,
    product_type_to_domain,
    to_domain,
)
from src.infrastructure.catalog.models import (
    AttributeChoiceModel,
    AttributeModel,
    ProductTypeAttributeModel,
    ProductTypeModel,
)

logger = structlog.get_logger(__name__)

# Eager-load an attribute's choices / a product type's ordered attribute links so
# the mappers never trigger a per-row query.
_PRODUCT_TYPE_PREFETCH = "attribute_links__attribute"


class DjangoAttributeRepository(AttributeRepository):
    """Persist attributes with the Django ORM, returning domain entities."""

    def add(self, attribute: Attribute) -> Attribute:
        model = apply_scalar_fields(attribute, AttributeModel())
        try:
            # The attribute and all its choices are one definition: persist them
            # together so a failed choice insert never leaves a half-built record.
            with transaction.atomic():
                model.save()
                self._save_choices(attribute, model)
        except IntegrityError as exc:
            # Unique-constraint violation on code -> domain-level conflict. Reaching
            # here means a concurrent insert won the race after the use case's
            # pre-check passed.
            logger.warning("attribute_insert_race_lost", code=attribute.code.value)
            raise AttributeAlreadyExistsError(attribute.code.value) from exc
        return to_domain(model)

    @staticmethod
    def _save_choices(attribute: Attribute, model: AttributeModel) -> None:
        AttributeChoiceModel.objects.bulk_create(
            AttributeChoiceModel(
                attribute=model,
                value=choice.value,
                label=choice.label,
                position=position,
            )
            for position, choice in enumerate(attribute.choices)
        )

    def get_by_code(self, code: str) -> Attribute:
        try:
            model = AttributeModel.objects.prefetch_related("choices").get(code=code)
        except AttributeModel.DoesNotExist as exc:
            raise AttributeNotFoundError(code) from exc
        return to_domain(model)

    def exists_by_code(self, code: str) -> bool:
        return AttributeModel.objects.filter(code=code).exists()

    def list_all(self) -> list[Attribute]:
        models = AttributeModel.objects.prefetch_related("choices").all()
        return [to_domain(model) for model in models]


class DjangoProductTypeRepository(ProductTypeRepository):
    """Persist product types with the Django ORM, returning domain entities."""

    def add(self, product_type: ProductType) -> ProductType:
        model = apply_product_type_scalar_fields(product_type, ProductTypeModel())
        try:
            # A product type and its ordered attribute assignments are one unit:
            # persist them together so a failed link insert leaves nothing behind.
            with transaction.atomic():
                model.save()
                self._link_attributes(product_type, model)
        except IntegrityError as exc:
            # Unique-constraint violation on code -> domain-level conflict (a
            # concurrent insert won the race after the use case's pre-check).
            logger.warning("product_type_insert_race_lost", code=product_type.code.value)
            raise ProductTypeAlreadyExistsError(product_type.code.value) from exc
        return self.get_by_code(product_type.code.value)

    @staticmethod
    def _link_attributes(product_type: ProductType, model: ProductTypeModel) -> None:
        # Resolve the referenced codes to rows in one query, preserving the
        # product type's declared order via the link position.
        codes = [attribute.value for attribute in product_type.attributes]
        by_code = {a.code: a for a in AttributeModel.objects.filter(code__in=codes)}
        links = []
        for position, attribute in enumerate(product_type.attributes):
            attribute_model = by_code.get(attribute.value)
            if attribute_model is None:
                # The use case validated existence; reaching here means the
                # attribute vanished concurrently. Surface it as a domain error.
                raise UnknownAttributeError(attribute.value)
            links.append(
                ProductTypeAttributeModel(
                    product_type=model, attribute=attribute_model, position=position
                )
            )
        ProductTypeAttributeModel.objects.bulk_create(links)

    def get_by_code(self, code: str) -> ProductType:
        try:
            model = ProductTypeModel.objects.prefetch_related(_PRODUCT_TYPE_PREFETCH).get(code=code)
        except ProductTypeModel.DoesNotExist as exc:
            raise ProductTypeNotFoundError(code) from exc
        return product_type_to_domain(model)

    def exists_by_code(self, code: str) -> bool:
        return ProductTypeModel.objects.filter(code=code).exists()

    def list_all(self) -> list[ProductType]:
        models = ProductTypeModel.objects.prefetch_related(_PRODUCT_TYPE_PREFETCH).all()
        return [product_type_to_domain(model) for model in models]
