"""Django ORM implementation of the catalog repository ports."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import structlog
from django.db import IntegrityError, transaction
from django.db.models import Min, Q, QuerySet

from src.application.catalog.ports import (
    AttributeRepository,
    CatalogImportWriter,
    CategoryRepository,
    ChannelReader,
    CollectionProductRepository,
    CollectionRepository,
    CollectionRuleRepository,
    PriceSummary,
    ProductCategoryRepository,
    ProductFilters,
    ProductImportItem,
    ProductPage,
    ProductQueryRepository,
    ProductRepository,
    ProductTypeRepository,
    StockRepository,
    VariantPriceRepository,
    VariantRepository,
)
from src.domain.catalog.entities import (
    Attribute,
    Category,
    Collection,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.enums import RuleOperator
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    InsufficientStockError,
    ParentCategoryNotFoundError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
    UnknownAttributeError,
    UnknownCategoryError,
    UnknownProductError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    CategorySlug,
    ChannelPrice,
    MediaAsset,
    Money,
    ProductCode,
    RuleCondition,
    StockQuantity,
)
from src.domain.inventory.exceptions import (
    InsufficientStockError as InventoryInsufficientStockError,
)
from src.infrastructure.catalog.mappers import (
    apply_category_scalar_fields,
    apply_collection_scalar_fields,
    apply_product_scalar_fields,
    apply_product_type_scalar_fields,
    apply_scalar_fields,
    apply_variant_scalar_fields,
    category_to_domain,
    collection_to_domain,
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
    CollectionModel,
    CollectionProductModel,
    CollectionRuleConditionModel,
    ProductAttributeValueModel,
    ProductCategoryModel,
    ProductModel,
    ProductTypeAttributeModel,
    ProductTypeModel,
    ProductVariantAttributeValueModel,
    ProductVariantMediaModel,
    ProductVariantModel,
    VariantPriceModel,
)
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.inventory.repositories import (
    DjangoStockLevelRepository,
    DjangoStockPolicyRepository,
    DjangoStockSourceRepository,
)
from src.infrastructure.tax.rates import SettingsTaxRateReader

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

    def set_published(self, code: str, is_published: bool) -> Product:
        # A single-column update on one row; the implicit statement-level atomicity
        # is enough (no child tables to keep consistent).
        try:
            model = (
                ProductModel.objects.select_related("product_type")
                .prefetch_related(_PRODUCT_VALUES_PREFETCH)
                .get(code=code)
            )
        except ProductModel.DoesNotExist as exc:
            raise ProductNotFoundError(code) from exc
        model.is_published = is_published
        model.save(update_fields=["is_published", "updated_at"])
        return product_to_domain(model)


class DjangoProductQueryRepository(ProductQueryRepository):
    """Read-optimised product browsing (filter / search / paginate) with the Django ORM."""

    def search(self, *, filters: ProductFilters, limit: int, offset: int) -> ProductPage:
        queryset = self._apply_filters(ProductModel.objects.all(), filters)
        # Count the full match set before windowing so the caller can paginate.
        total = queryset.count()
        window = (
            queryset.select_related("product_type")
            .prefetch_related(_PRODUCT_VALUES_PREFETCH)
            .order_by("code")[offset : offset + limit]
        )
        items = tuple(product_to_domain(model) for model in window)
        return ProductPage(items=items, total=total)

    def price_summaries(self, *, codes: Sequence[str], channel: str) -> dict[str, PriceSummary]:
        if not codes:
            return {}
        # Lowest in-channel base price per product (its "from" price). All prices in
        # one channel share a currency, so grouping by currency yields one row/code.
        priced = (
            VariantPriceModel.objects.filter(channel_slug=channel, variant__product__code__in=codes)
            .values("variant__product__code", "currency_code")
            .annotate(from_amount=Min("amount"))
        )
        from_by_code = {
            row["variant__product__code"]: Money(
                amount=row["from_amount"], currency=row["currency_code"]
            )
            for row in priced
        }
        # Buyable = some variant is priced in this channel AND either has stock available
        # to promise (on-hand minus reserved across sources > 0) OR is backorderable (sold
        # beyond physical stock by policy). A fully reserved, non-backorderable variant
        # reads as out of stock.
        priced_variants = list(
            ProductVariantModel.objects.filter(
                product__code__in=codes,
                prices__channel_slug=channel,
            )
            .values_list("product__code", "sku")
            .distinct()
        )
        skus = [sku for _, sku in priced_variants]
        available_by_sku = DjangoStockLevelRepository().available_for_skus(skus)
        backorderable = DjangoStockPolicyRepository().backorderable_skus(skus)
        available_codes = {
            code
            for code, sku in priced_variants
            if available_by_sku.get(sku, 0) > 0 or sku in backorderable
        }
        # Resolve each product's tax-class rate in the channel (None for an exempt product or
        # an untaxed channel) so the storefront can show a "prices include X% VAT" note.
        tax_reader = SettingsTaxRateReader()
        class_by_code = dict(
            ProductModel.objects.filter(code__in=codes).values_list("code", "tax_class")
        )
        rate_by_code: dict[str, Decimal | None] = {}
        for code in codes:
            rate = tax_reader.rate_for(channel, class_by_code.get(code, "standard"))
            rate_by_code[code] = rate.value if rate is not None else None
        return {
            code: PriceSummary(
                from_price=from_by_code.get(code),
                available=code in available_codes,
                tax_rate=rate_by_code[code],
            )
            for code in codes
        }

    @staticmethod
    def _apply_filters(
        queryset: QuerySet[ProductModel], filters: ProductFilters
    ) -> QuerySet[ProductModel]:
        # Each criterion narrows the set (AND). Membership filters join the through
        # tables; the per-(product, target) uniqueness constraints mean no row is
        # duplicated, but distinct() keeps the result safe under future joins.
        if filters.published_only:
            queryset = queryset.filter(is_published=True)
        if filters.product_type is not None:
            queryset = queryset.filter(product_type__code=filters.product_type)
        if filters.category is not None:
            queryset = queryset.filter(category_links__category__slug=filters.category)
        if filters.collection is not None:
            queryset = queryset.filter(collection_links__collection__slug=filters.collection)
        if filters.search is not None:
            # The ORM parameterises these, so the user-supplied term cannot inject SQL.
            queryset = queryset.filter(
                Q(name__icontains=filters.search) | Q(code__icontains=filters.search)
            )
        queryset = DjangoProductQueryRepository._apply_price_range(queryset, filters)
        return queryset.distinct()

    @staticmethod
    def _apply_price_range(
        queryset: QuerySet[ProductModel], filters: ProductFilters
    ) -> QuerySet[ProductModel]:
        # Price is per-variant, per-channel, so a range only makes sense within a
        # channel. Filter on the product's *lowest* in-channel base price -- the same
        # "from" price shown on the card -- so the result matches what the shopper sees.
        if filters.channel is None or (filters.min_price is None and filters.max_price is None):
            return queryset
        queryset = queryset.annotate(
            from_amount=Min(
                "variants__prices__amount",
                filter=Q(variants__prices__channel_slug=filters.channel),
            )
        )
        if filters.min_price is not None:
            queryset = queryset.filter(from_amount__gte=filters.min_price)
        if filters.max_price is not None:
            queryset = queryset.filter(from_amount__lte=filters.max_price)
        return queryset

    def get_published_by_code(self, code: str) -> Product:
        try:
            model = (
                ProductModel.objects.select_related("product_type")
                .prefetch_related(_PRODUCT_VALUES_PREFETCH)
                .get(code=code, is_published=True)
            )
        except ProductModel.DoesNotExist as exc:
            # A draft (or a genuinely missing product) is a 404: the existence of an
            # unpublished product is never leaked through the public read surface.
            raise ProductNotFoundError(code) from exc
        return product_to_domain(model)

    def primary_images(self, *, codes: Sequence[str]) -> dict[str, MediaAsset]:
        if not codes:
            return {}
        # Order so the first row seen for each code is its primary image: earliest
        # variant (lowest SKU), then that variant's first media asset (lowest
        # position). One query for the whole page; the first hit per code wins.
        rows = (
            ProductVariantMediaModel.objects.filter(variant__product__code__in=codes)
            .order_by("variant__product__code", "variant__sku", "position")
            .values_list("variant__product__code", "url", "alt_text")
        )
        images: dict[str, MediaAsset] = {}
        for code, url, alt_text in rows:
            if code not in images:
                images[code] = MediaAsset(url=url, alt_text=alt_text)
        return images


class DjangoCatalogImportWriter(CatalogImportWriter):
    """Persist a validated bulk product import with the Django ORM (all-or-nothing)."""

    def __init__(self) -> None:
        self._products = DjangoProductRepository()
        self._categories = DjangoProductCategoryRepository()

    def create_products(self, items: Sequence[ProductImportItem]) -> None:
        # One transaction spans the whole batch, so any failure (e.g. an insert race
        # lost after the use case validated the codes as free) rolls every product and
        # category link back -- a partial import is impossible. The per-aggregate
        # writers' own atomic blocks nest under this one as savepoints.
        with transaction.atomic():
            for item in items:
                self._products.add(item.product)
                if item.categories:
                    self._categories.replace(item.product.code.value, item.categories)


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


class DjangoCollectionRepository(CollectionRepository):
    """Persist catalog collections with the Django ORM, returning domain entities."""

    def add(self, collection: Collection) -> Collection:
        # A collection is a single row (no child tables), so no transaction wrapper
        # is needed: the one INSERT is already atomic.
        model = apply_collection_scalar_fields(collection, CollectionModel())
        try:
            model.save()
        except IntegrityError as exc:
            # Unique-constraint violation on slug -> domain-level conflict (a
            # concurrent insert won the race after the use case's pre-check).
            logger.warning("collection_insert_race_lost", slug=collection.slug.value)
            raise CollectionAlreadyExistsError(collection.slug.value) from exc
        return collection_to_domain(model)

    def get_by_slug(self, slug: str) -> Collection:
        try:
            model = CollectionModel.objects.get(slug=slug)
        except CollectionModel.DoesNotExist as exc:
            raise CollectionNotFoundError(slug) from exc
        return collection_to_domain(model)

    def exists_by_slug(self, slug: str) -> bool:
        return CollectionModel.objects.filter(slug=slug).exists()

    def list_all(self) -> list[Collection]:
        return [collection_to_domain(model) for model in CollectionModel.objects.all()]


class DjangoProductCategoryRepository(ProductCategoryRepository):
    """Persist a product's category membership with the Django ORM."""

    def replace(
        self, product_code: str, categories: Sequence[CategorySlug]
    ) -> tuple[CategorySlug, ...]:
        # Replacing the membership (clear + reinsert) must be all-or-nothing, so a
        # failed reinsert never leaves the product with a half-updated set. The
        # product row is locked so two concurrent replaces of the same product
        # serialize instead of interleaving into a unique-constraint error.
        with transaction.atomic():
            product = self._lock_product(product_code)
            ProductCategoryModel.objects.filter(product=product).delete()
            self._insert_links(product, categories)
        return self.list_for_product(product_code)

    @staticmethod
    def _lock_product(product_code: str) -> ProductModel:
        try:
            return ProductModel.objects.select_for_update().get(code=product_code)
        except ProductModel.DoesNotExist as exc:
            raise ProductNotFoundError(product_code) from exc

    @staticmethod
    def _insert_links(product: ProductModel, categories: Sequence[CategorySlug]) -> None:
        # Resolve every referenced slug to a row in one query, preserving the
        # requested order via the link position.
        slugs = [category.value for category in categories]
        by_slug = {c.slug: c for c in CategoryModel.objects.filter(slug__in=slugs)}
        rows = []
        for position, category in enumerate(categories):
            category_model = by_slug.get(category.value)
            if category_model is None:
                # The use case validated existence; reaching here means the category
                # vanished concurrently. Surface it as a domain error and roll back.
                raise UnknownCategoryError(category.value)
            rows.append(
                ProductCategoryModel(product=product, category=category_model, position=position)
            )
        ProductCategoryModel.objects.bulk_create(rows)

    def list_for_product(self, product_code: str) -> tuple[CategorySlug, ...]:
        links = (
            ProductCategoryModel.objects.select_related("category")
            .filter(product__code=product_code)
            .order_by("position")
        )
        return tuple(CategorySlug(link.category.slug) for link in links)

    def list_for_products(
        self, product_codes: Sequence[str]
    ) -> dict[str, tuple[CategorySlug, ...]]:
        # One query for the whole set, grouped in Python by product code and kept
        # in assignment order, so listing a catalog is a single round trip. Every
        # requested code is present; one with no membership maps to an empty tuple.
        grouped: dict[str, list[CategorySlug]] = {code: [] for code in product_codes}
        if not grouped:
            return {}
        links = (
            ProductCategoryModel.objects.select_related("category", "product")
            .filter(product__code__in=list(grouped))
            .order_by("position")
        )
        for link in links:
            grouped[link.product.code].append(CategorySlug(link.category.slug))
        return {code: tuple(slugs) for code, slugs in grouped.items()}


class DjangoCollectionProductRepository(CollectionProductRepository):
    """Persist a collection's product membership with the Django ORM."""

    def replace(
        self, collection_slug: str, products: Sequence[ProductCode]
    ) -> tuple[ProductCode, ...]:
        # Replacing the membership (clear + reinsert) must be all-or-nothing, so a
        # failed reinsert never leaves the collection with a half-updated list. The
        # collection row is locked so two concurrent replaces of the same collection
        # serialize instead of interleaving into a unique-constraint error.
        with transaction.atomic():
            collection = self._lock_collection(collection_slug)
            CollectionProductModel.objects.filter(collection=collection).delete()
            self._insert_links(collection, products)
        return self.list_for_collection(collection_slug)

    @staticmethod
    def _lock_collection(collection_slug: str) -> CollectionModel:
        try:
            return CollectionModel.objects.select_for_update().get(slug=collection_slug)
        except CollectionModel.DoesNotExist as exc:
            raise CollectionNotFoundError(collection_slug) from exc

    @staticmethod
    def _insert_links(collection: CollectionModel, products: Sequence[ProductCode]) -> None:
        # Resolve every referenced code to a row in one query, preserving the
        # requested order via the link position.
        codes = [product.value for product in products]
        by_code = {p.code: p for p in ProductModel.objects.filter(code__in=codes)}
        rows = []
        for position, product in enumerate(products):
            product_model = by_code.get(product.value)
            if product_model is None:
                # The use case validated existence; reaching here means the product
                # vanished concurrently. Surface it as a domain error and roll back.
                raise UnknownProductError(product.value)
            rows.append(
                CollectionProductModel(
                    collection=collection, product=product_model, position=position
                )
            )
        CollectionProductModel.objects.bulk_create(rows)

    def list_for_collection(self, collection_slug: str) -> tuple[ProductCode, ...]:
        links = (
            CollectionProductModel.objects.select_related("product")
            .filter(collection__slug=collection_slug)
            .order_by("position")
        )
        return tuple(ProductCode(link.product.code) for link in links)


class DjangoCollectionRuleRepository(CollectionRuleRepository):
    """Persist a rule-based collection's membership rule with the Django ORM."""

    def replace(
        self, collection_slug: str, conditions: Sequence[RuleCondition]
    ) -> tuple[RuleCondition, ...]:
        # Replacing the rule (clear + reinsert) must be all-or-nothing, so a failed
        # reinsert never leaves the collection with a half-updated rule. The
        # collection row is locked so two concurrent replaces of the same collection
        # serialize instead of interleaving into a unique-constraint error.
        with transaction.atomic():
            collection = self._lock_collection(collection_slug)
            CollectionRuleConditionModel.objects.filter(collection=collection).delete()
            self._insert_conditions(collection, conditions)
        return self.list_for_collection(collection_slug)

    @staticmethod
    def _lock_collection(collection_slug: str) -> CollectionModel:
        try:
            return CollectionModel.objects.select_for_update().get(slug=collection_slug)
        except CollectionModel.DoesNotExist as exc:
            raise CollectionNotFoundError(collection_slug) from exc

    @staticmethod
    def _insert_conditions(
        collection: CollectionModel, conditions: Sequence[RuleCondition]
    ) -> None:
        # Resolve every referenced attribute code to a row in one query, preserving
        # the requested order via the condition position.
        codes = [condition.attribute.value for condition in conditions]
        by_code = {a.code: a for a in AttributeModel.objects.filter(code__in=codes)}
        rows = []
        for position, condition in enumerate(conditions):
            attribute_model = by_code.get(condition.attribute.value)
            if attribute_model is None:
                # The use case validated existence; reaching here means the attribute
                # vanished concurrently. Surface it as a domain error and roll back.
                raise UnknownAttributeError(condition.attribute.value)
            rows.append(
                CollectionRuleConditionModel(
                    collection=collection,
                    attribute=attribute_model,
                    operator=condition.operator.value,
                    value=condition.value,
                    position=position,
                )
            )
        CollectionRuleConditionModel.objects.bulk_create(rows)

    def list_for_collection(self, collection_slug: str) -> tuple[RuleCondition, ...]:
        conditions = (
            CollectionRuleConditionModel.objects.select_related("attribute")
            .filter(collection__slug=collection_slug)
            .order_by("position")
        )
        return tuple(
            RuleCondition(
                attribute=AttributeCode(condition.attribute.code),
                operator=RuleOperator(condition.operator),
                value=condition.value,
            )
            for condition in conditions
        )


class DjangoVariantPriceRepository(VariantPriceRepository):
    """Persist a variant's per-channel base prices with the Django ORM."""

    def replace(self, sku: str, prices: Sequence[ChannelPrice]) -> tuple[ChannelPrice, ...]:
        # Replacing the prices (clear + reinsert) must be all-or-nothing, so a failed
        # reinsert never leaves the variant with a half-updated price set. The variant
        # row is locked so two concurrent replaces of the same variant serialize
        # instead of interleaving into a unique-constraint error.
        with transaction.atomic():
            variant = self._lock_variant(sku)
            VariantPriceModel.objects.filter(variant=variant).delete()
            self._insert_prices(variant, prices)
        return self.list_for_variant(sku)

    @staticmethod
    def _lock_variant(sku: str) -> ProductVariantModel:
        try:
            return ProductVariantModel.objects.select_for_update().get(sku=sku)
        except ProductVariantModel.DoesNotExist as exc:
            raise VariantNotFoundError(sku) from exc

    @staticmethod
    def _insert_prices(variant: ProductVariantModel, prices: Sequence[ChannelPrice]) -> None:
        VariantPriceModel.objects.bulk_create(
            VariantPriceModel(
                variant=variant,
                channel_slug=price.channel,
                currency_code=price.money.currency,
                amount=price.money.amount,
            )
            for price in prices
        )

    def list_for_variant(self, sku: str) -> tuple[ChannelPrice, ...]:
        rows = VariantPriceModel.objects.filter(variant__sku=sku).order_by("channel_slug")
        return tuple(
            ChannelPrice(
                channel=row.channel_slug,
                money=Money(amount=row.amount, currency=row.currency_code),
            )
            for row in rows
        )


class DjangoChannelReader(ChannelReader):
    """Read a channel's currency from the channel context, for catalog pricing."""

    def currency_of(self, channel_slug: str) -> str | None:
        return (
            ChannelModel.objects.filter(slug=channel_slug)
            .values_list("currency_code", flat=True)
            .first()
        )


class DjangoStockRepository(StockRepository):
    """Expose a variant's on-hand stock over the inventory context's default source.

    On-hand stock is owned by the inventory context (multi-source, with reservations);
    this catalog adapter keeps the simple single-count surface the admin stock endpoints
    expose, operating on the default source. The variant must exist
    (``VariantNotFoundError``); a lock on the variant row serializes a set against a
    concurrent adjust, and the inventory adapter takes the stock-level row lock.
    """

    def __init__(self) -> None:
        self._levels = DjangoStockLevelRepository()
        self._sources = DjangoStockSourceRepository()

    def get_quantity(self, sku: str) -> StockQuantity:
        return StockQuantity(self._levels.total_on_hand(sku))

    def set_quantity(self, sku: str, quantity: StockQuantity) -> StockQuantity:
        with transaction.atomic():
            self._lock_variant(sku)
            source = self._sources.ensure_default()
            self._levels.set_on_hand(sku, source, quantity.value)
        return quantity

    def adjust_quantity(self, sku: str, delta: int) -> StockQuantity:
        # The variant-row lock serializes concurrent set/adjust; the inventory adapter's
        # own row lock serializes the physical read-modify-write. The no-below-zero rule
        # is the inventory domain's, translated back to the catalog's error here.
        with transaction.atomic():
            self._lock_variant(sku)
            source = self._sources.ensure_default()
            try:
                self._levels.adjust_on_hand(sku, source, delta)
            except InventoryInsufficientStockError as exc:
                raise InsufficientStockError(available=exc.available, delta=delta) from exc
            return StockQuantity(self._levels.total_on_hand(sku))

    @staticmethod
    def _lock_variant(sku: str) -> ProductVariantModel:
        try:
            return ProductVariantModel.objects.select_for_update().get(sku=sku)
        except ProductVariantModel.DoesNotExist as exc:
            raise VariantNotFoundError(sku) from exc
