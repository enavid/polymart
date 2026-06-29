"""Django ORM implementation of the catalog repository ports."""

from __future__ import annotations

import structlog
from django.db import IntegrityError, transaction

from src.application.catalog.ports import (
    AttributeRepository,
    CategoryRepository,
    ProductRepository,
    ProductTypeRepository,
    VariantRepository,
)
from src.domain.catalog.entities import (
    Attribute,
    Category,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    ParentCategoryNotFoundError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
    UnknownAttributeError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import AttributeCode
from src.infrastructure.catalog.mappers import (
    apply_category_scalar_fields,
    apply_product_scalar_fields,
    apply_product_type_scalar_fields,
    apply_scalar_fields,
    apply_variant_scalar_fields,
    category_to_domain,
    product_to_domain,
    product_type_to_domain,
    to_domain,
    variant_to_domain,
)
from src.infrastructure.catalog.models import (
    PRODUCT_ATTRIBUTE_KIND,
    VARIANT_ATTRIBUTE_KIND,
    AttributeChoiceModel,
    AttributeModel,
    CategoryModel,
    ProductAttributeValueModel,
    ProductModel,
    ProductTypeAttributeModel,
    ProductTypeModel,
    ProductVariantAttributeValueModel,
    ProductVariantMediaModel,
    ProductVariantModel,
)

logger = structlog.get_logger(__name__)

# Eager-load an attribute's choices / a product type's ordered attribute links so
# the mappers never trigger a per-row query.
_PRODUCT_TYPE_PREFETCH = "attribute_links__attribute"
_PRODUCT_VALUES_PREFETCH = "attribute_values__attribute"
# A variant's option values and media are both loaded up front so the mapper never
# triggers a per-row query.
_VARIANT_PREFETCH = ("attribute_values__attribute", "media")


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

    @classmethod
    def _link_attributes(cls, product_type: ProductType, model: ProductTypeModel) -> None:
        # Resolve every referenced code (both levels) to a row in one query,
        # preserving each level's declared order via the link position.
        codes = [
            attribute.value
            for attribute in (*product_type.attributes, *product_type.variant_attributes)
        ]
        by_code = {a.code: a for a in AttributeModel.objects.filter(code__in=codes)}
        links = [
            *cls._level_links(product_type.attributes, model, by_code, PRODUCT_ATTRIBUTE_KIND),
            *cls._level_links(
                product_type.variant_attributes, model, by_code, VARIANT_ATTRIBUTE_KIND
            ),
        ]
        ProductTypeAttributeModel.objects.bulk_create(links)

    @staticmethod
    def _level_links(
        attributes: tuple[AttributeCode, ...],
        model: ProductTypeModel,
        by_code: dict[str, AttributeModel],
        kind: str,
    ) -> list[ProductTypeAttributeModel]:
        links = []
        for position, attribute in enumerate(attributes):
            attribute_model = by_code.get(attribute.value)
            if attribute_model is None:
                # The use case validated existence; reaching here means the
                # attribute vanished concurrently. Surface it as a domain error.
                raise UnknownAttributeError(attribute.value)
            links.append(
                ProductTypeAttributeModel(
                    product_type=model, attribute=attribute_model, kind=kind, position=position
                )
            )
        return links

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


class DjangoProductRepository(ProductRepository):
    """Persist products with the Django ORM, returning domain entities."""

    def add(self, product: Product) -> Product:
        try:
            # A product and all its attribute values are one unit: persist them
            # together so a failed value insert leaves nothing behind.
            with transaction.atomic():
                model = self._build_model(product)
                model.save()
                self._save_values(product, model)
        except IntegrityError as exc:
            # Unique-constraint violation on code -> domain-level conflict (a
            # concurrent insert won the race after the use case's pre-check).
            logger.warning("product_insert_race_lost", code=product.code.value)
            raise ProductAlreadyExistsError(product.code.value) from exc
        return self.get_by_code(product.code.value)

    @staticmethod
    def _build_model(product: Product) -> ProductModel:
        code = product.product_type.value
        try:
            product_type = ProductTypeModel.objects.get(code=code)
        except ProductTypeModel.DoesNotExist as exc:
            # The use case resolved the type; reaching here means it vanished
            # concurrently. Surface it as a domain error and roll the insert back.
            raise ProductTypeNotFoundError(code) from exc
        return apply_product_scalar_fields(product, ProductModel(product_type=product_type))

    @staticmethod
    def _save_values(product: Product, model: ProductModel) -> None:
        # Resolve the referenced attribute codes to rows in one query, preserving
        # the conformance-checked order via the value position.
        codes = [value.attribute.value for value in product.values]
        by_code = {a.code: a for a in AttributeModel.objects.filter(code__in=codes)}
        rows = []
        for position, value in enumerate(product.values):
            attribute_model = by_code.get(value.attribute.value)
            if attribute_model is None:
                # The use case validated existence; reaching here means the
                # attribute vanished concurrently. Surface it as a domain error.
                raise UnknownAttributeError(value.attribute.value)
            rows.append(
                ProductAttributeValueModel(
                    product=model,
                    attribute=attribute_model,
                    value=value.value,
                    position=position,
                )
            )
        ProductAttributeValueModel.objects.bulk_create(rows)

    def get_by_code(self, code: str) -> Product:
        try:
            model = (
                ProductModel.objects.select_related("product_type")
                .prefetch_related(_PRODUCT_VALUES_PREFETCH)
                .get(code=code)
            )
        except ProductModel.DoesNotExist as exc:
            raise ProductNotFoundError(code) from exc
        return product_to_domain(model)

    def exists_by_code(self, code: str) -> bool:
        return ProductModel.objects.filter(code=code).exists()

    def list_all(self) -> list[Product]:
        models = (
            ProductModel.objects.select_related("product_type")
            .prefetch_related(_PRODUCT_VALUES_PREFETCH)
            .all()
        )
        return [product_to_domain(model) for model in models]


class DjangoVariantRepository(VariantRepository):
    """Persist product variants with the Django ORM, returning domain entities."""

    def add(self, variant: ProductVariant) -> ProductVariant:
        try:
            # A variant and all its option values are one unit: persist them
            # together so a failed value insert leaves nothing behind.
            with transaction.atomic():
                model = self._build_model(variant)
                model.save()
                self._save_values(variant, model)
                self._save_media(variant, model)
        except IntegrityError as exc:
            # Unique-constraint violation on SKU -> domain-level conflict (a
            # concurrent insert won the race after the use case's pre-check).
            logger.warning("variant_insert_race_lost", sku=variant.sku.value)
            raise VariantAlreadyExistsError(variant.sku.value) from exc
        return self.get_by_sku(variant.sku.value)

    @staticmethod
    def _build_model(variant: ProductVariant) -> ProductVariantModel:
        code = variant.product.value
        try:
            product = ProductModel.objects.get(code=code)
        except ProductModel.DoesNotExist as exc:
            # The use case resolved the product; reaching here means it vanished
            # concurrently. Surface it as a domain error (no row is written).
            raise ProductNotFoundError(code) from exc
        return apply_variant_scalar_fields(variant, ProductVariantModel(product=product))

    @staticmethod
    def _save_values(variant: ProductVariant, model: ProductVariantModel) -> None:
        # Resolve the referenced attribute codes to rows in one query, preserving
        # the conformance-checked order via the value position.
        codes = [value.attribute.value for value in variant.values]
        by_code = {a.code: a for a in AttributeModel.objects.filter(code__in=codes)}
        rows = []
        for position, value in enumerate(variant.values):
            attribute_model = by_code.get(value.attribute.value)
            if attribute_model is None:
                # The use case validated existence; reaching here means the
                # attribute vanished concurrently. Surface it as a domain error.
                raise UnknownAttributeError(value.attribute.value)
            rows.append(
                ProductVariantAttributeValueModel(
                    variant=model,
                    attribute=attribute_model,
                    value=value.value,
                    position=position,
                )
            )
        ProductVariantAttributeValueModel.objects.bulk_create(rows)

    @staticmethod
    def _save_media(variant: ProductVariant, model: ProductVariantModel) -> None:
        ProductVariantMediaModel.objects.bulk_create(
            ProductVariantMediaModel(
                variant=model,
                url=asset.url,
                alt_text=asset.alt_text,
                position=position,
            )
            for position, asset in enumerate(variant.media)
        )

    def get_by_sku(self, sku: str) -> ProductVariant:
        try:
            model = (
                ProductVariantModel.objects.select_related("product")
                .prefetch_related(*_VARIANT_PREFETCH)
                .get(sku=sku)
            )
        except ProductVariantModel.DoesNotExist as exc:
            raise VariantNotFoundError(sku) from exc
        return variant_to_domain(model)

    def exists_by_sku(self, sku: str) -> bool:
        return ProductVariantModel.objects.filter(sku=sku).exists()

    def list_for_product(self, product_code: str) -> list[ProductVariant]:
        models = (
            ProductVariantModel.objects.select_related("product")
            .prefetch_related(*_VARIANT_PREFETCH)
            .filter(product__code=product_code)
        )
        return [variant_to_domain(model) for model in models]


class DjangoCategoryRepository(CategoryRepository):
    """Persist catalog categories with the Django ORM, returning domain entities."""

    def add(self, category: Category) -> Category:
        # A category is a single row (no child tables), so no transaction wrapper is
        # needed: the one INSERT is already atomic.
        model = apply_category_scalar_fields(category, CategoryModel())
        model.parent = self._resolve_parent(category)
        try:
            model.save()
        except IntegrityError as exc:
            # Unique-constraint violation on slug -> domain-level conflict (a
            # concurrent insert won the race after the use case's pre-check).
            logger.warning("category_insert_race_lost", slug=category.slug.value)
            raise CategoryAlreadyExistsError(category.slug.value) from exc
        return self.get_by_slug(category.slug.value)

    @staticmethod
    def _resolve_parent(category: Category) -> CategoryModel | None:
        if category.parent is None:
            return None
        slug = category.parent.value
        try:
            return CategoryModel.objects.get(slug=slug)
        except CategoryModel.DoesNotExist as exc:
            # The use case validated existence; reaching here means the parent
            # vanished concurrently. Surface it as a domain error (no row written).
            raise ParentCategoryNotFoundError(slug) from exc

    def get_by_slug(self, slug: str) -> Category:
        try:
            model = CategoryModel.objects.select_related("parent").get(slug=slug)
        except CategoryModel.DoesNotExist as exc:
            raise CategoryNotFoundError(slug) from exc
        return category_to_domain(model)

    def exists_by_slug(self, slug: str) -> bool:
        return CategoryModel.objects.filter(slug=slug).exists()

    def list_all(self) -> list[Category]:
        models = CategoryModel.objects.select_related("parent").all()
        return [category_to_domain(model) for model in models]
