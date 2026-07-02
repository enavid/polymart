"""Seed a deterministic dataset for end-to-end (browser) tests.

The Playwright suite drives the *real* stack, so the database must contain a
known, stable fixture: two users (a shopper and a staff member with the full set
of admin roles), a channel, and a small published catalog (product type,
products, variants with per-channel prices and stock, categories, a collection).

The command is **idempotent** -- running it twice leaves the same data, never a
duplicate or an error -- so it is safe to call before every E2E run. It is
guarded to refuse to run outside DEBUG, so it can never seed a production
database even if it were somehow reachable there.

The constants below are the single source of truth for the fixture. They are
mirrored in ``frontend/tests/e2e/fixtures/seed.ts``; the two must stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from src.domain.access.registry import (
    ACCESS_ADMIN_ROLE,
    CATALOG_ADMIN_ROLE,
    CHANNEL_ADMIN_ROLE,
)
from src.domain.catalog.entities import (
    Category,
    Collection,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.value_objects import (
    CategorySlug,
    ChannelPrice,
    CollectionSlug,
    Money,
    ProductCode,
    ProductTypeCode,
    Sku,
    StockQuantity,
)
from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.domain.identity.value_objects import PhoneNumber
from src.infrastructure.address.models import AddressModel
from src.infrastructure.cart.models import CartModel
from src.infrastructure.catalog.models import (
    CategoryModel,
    CollectionModel,
    ProductModel,
    ProductTypeModel,
    ProductVariantModel,
)
from src.infrastructure.catalog.repositories import (
    DjangoCategoryRepository,
    DjangoCollectionProductRepository,
    DjangoCollectionRepository,
    DjangoProductCategoryRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.channel.repositories import DjangoChannelRepository
from src.infrastructure.identity.models import User
from src.infrastructure.order.models import OrderModel
from src.interface.api.access.container import build_assign_role

logger = structlog.get_logger(__name__)

# --- Fixture constants (mirror frontend/tests/e2e/fixtures/seed.ts) ---
CHANNEL_SLUG = "ir-main"
CHANNEL_CURRENCY = "IRR"

SHOPPER_PHONE = "09120000001"
SHOPPER_PASSWORD = "shopper-pass-123"
STAFF_PHONE = "09120000009"
STAFF_PASSWORD = "staff-pass-123"

PRODUCT_TYPE_CODE = "coffee"

CATEGORY_ROOT = "hot-drinks"
CATEGORY_CHILD = "coffee-beans"
COLLECTION_SLUG = "featured"


# A channel the storefront is NOT viewed in, used to seed a variant that is
# priced somewhere but unavailable in the main channel.
OTHER_CHANNEL_SLUG = "ir-secondary"


@dataclass(frozen=True)
class _Variant:
    sku: str
    name: str
    price: str
    stock: int
    # The channel the price is written in. A variant priced in a channel other
    # than the storefront's is "unavailable in this channel" on the PDP.
    channel: str = CHANNEL_SLUG


@dataclass(frozen=True)
class _Product:
    code: str
    name: str
    variants: tuple[_Variant, ...]
    # Free-form metadata rendered on the storefront PDP (so the detail page has
    # real content, not just a variant list).
    description: str = ""


# A published catalog with enough shape to exercise the storefront: multiple
# products, multiple variants, an out-of-stock line, and a range of prices.
PRODUCTS: tuple[_Product, ...] = (
    _Product(
        code="house-blend",
        name="House Blend",
        description="A balanced, everyday medium roast with notes of cocoa and citrus.",
        variants=(
            _Variant(sku="HB-250", name="250g", price="120000.00", stock=30),
            _Variant(sku="HB-500", name="500g", price="200000.00", stock=10),
            # Priced only in another channel, so it is unavailable (not
            # purchasable) in the storefront's channel -- exercises that UI path.
            _Variant(
                sku="HB-1000",
                name="1kg",
                price="360000.00",
                stock=8,
                channel=OTHER_CHANNEL_SLUG,
            ),
        ),
    ),
    _Product(
        code="dark-roast",
        name="Dark Roast",
        description="A bold, full-bodied dark roast with a smoky finish.",
        variants=(_Variant(sku="DR-250", name="250g", price="150000.00", stock=5),),
    ),
    _Product(
        code="light-roast",
        name="Light Roast",
        description="A bright, delicate light roast with floral aromatics.",
        # Deliberately out of stock, to exercise the empty/zero-stock UI path.
        variants=(_Variant(sku="LR-250", name="250g", price="100000.00", stock=0),),
    ),
)


class Command(BaseCommand):
    help = "Seed a deterministic dataset for end-to-end browser tests (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_e2e refuses to run outside DEBUG -- it is a test fixture, "
                "never for a production database."
            )

        with transaction.atomic():
            self._seed_users()
            self._seed_channel()
            self._seed_catalog()

        logger.info("e2e_seed_completed", channel=CHANNEL_SLUG, products=len(PRODUCTS))
        self.stdout.write(self.style.SUCCESS("E2E seed complete."))

    # -- users -------------------------------------------------------------
    def _seed_users(self) -> None:
        # Go through the manager's create_user so the phone number is normalised
        # exactly as login expects (a raw insert would store an un-normalised
        # phone that the login lookup can never match).
        shopper, created = self._ensure_user(SHOPPER_PHONE, SHOPPER_PASSWORD, "Shopper")
        if not created:
            shopper.set_password(SHOPPER_PASSWORD)
            shopper.save(update_fields=["password"])

        staff, created = self._ensure_user(STAFF_PHONE, STAFF_PASSWORD, "Staff")
        if not created:
            staff.set_password(STAFF_PASSWORD)
        if not staff.is_staff:
            staff.is_staff = True
        staff.save()

        for role in (CATALOG_ADMIN_ROLE, ACCESS_ADMIN_ROLE, CHANNEL_ADMIN_ROLE):
            build_assign_role().execute(user_id=staff.pk, role_name=role)

        # Start every E2E run from an empty shopper cart, no prior orders, and an
        # empty address book, so the cart/checkout/address specs assert against a
        # known state regardless of what a previous run left behind. Stock is
        # re-set to the fixture values below in _seed_products, so deleting orders
        # (which never restores stock) is safe.
        CartModel.objects.filter(owner_id=shopper.pk).delete()
        OrderModel.objects.filter(owner_id=shopper.pk).delete()
        AddressModel.objects.filter(owner_id=shopper.pk).delete()

    @staticmethod
    def _ensure_user(phone: str, password: str, full_name: str) -> tuple[User, bool]:
        # create_user stores the phone in canonical E.164 form, so the
        # idempotency lookup must use the same canonical form -- looking up the
        # raw "09..." form would miss on a second run and re-create (a duplicate).
        canonical = PhoneNumber(phone).value
        existing = User.objects.filter(phone_number=canonical).first()
        if existing is None:
            created = User.objects.create_user(
                phone_number=phone, password=password, full_name=full_name
            )
            return created, True
        return existing, False

    # -- channel -----------------------------------------------------------
    @staticmethod
    def _seed_channel() -> None:
        if ChannelModel.objects.filter(slug=CHANNEL_SLUG).exists():
            return
        DjangoChannelRepository().add(
            Channel(
                slug=ChannelSlug(CHANNEL_SLUG),
                name="Iran Main",
                currency=Currency(CHANNEL_CURRENCY),
            )
        )

    # -- catalog -----------------------------------------------------------
    def _seed_catalog(self) -> None:
        self._seed_product_type()
        self._seed_categories()
        self._seed_products()
        self._seed_collection()

    @staticmethod
    def _seed_product_type() -> None:
        if ProductTypeModel.objects.filter(code=PRODUCT_TYPE_CODE).exists():
            return
        DjangoProductTypeRepository().add(
            ProductType(code=ProductTypeCode(PRODUCT_TYPE_CODE), name="Coffee")
        )

    @staticmethod
    def _seed_categories() -> None:
        repo = DjangoCategoryRepository()
        if not CategoryModel.objects.filter(slug=CATEGORY_ROOT).exists():
            repo.add(Category(slug=CategorySlug(CATEGORY_ROOT), name="Hot Drinks"))
        if not CategoryModel.objects.filter(slug=CATEGORY_CHILD).exists():
            repo.add(
                Category(
                    slug=CategorySlug(CATEGORY_CHILD),
                    name="Coffee Beans",
                    parent=CategorySlug(CATEGORY_ROOT),
                )
            )

    def _seed_products(self) -> None:
        products = DjangoProductRepository()
        variants = DjangoVariantRepository()
        prices = DjangoVariantPriceRepository()
        stock = DjangoStockRepository()
        categories = DjangoProductCategoryRepository()

        for product in PRODUCTS:
            if not ProductModel.objects.filter(code=product.code).exists():
                products.add(
                    Product(
                        code=ProductCode(product.code),
                        name=product.name,
                        product_type=ProductTypeCode(PRODUCT_TYPE_CODE),
                    )
                )
            # Idempotently ensure the storefront description (metadata) even when
            # the product already exists from an earlier seed run.
            ProductModel.objects.filter(code=product.code).update(
                metadata={"description": product.description}
            )
            for variant in product.variants:
                if not ProductVariantModel.objects.filter(sku=variant.sku).exists():
                    variants.add(
                        ProductVariant(
                            product=ProductCode(product.code),
                            sku=Sku(variant.sku),
                            name=variant.name,
                        )
                    )
                prices.replace(
                    variant.sku,
                    (
                        ChannelPrice(
                            channel=variant.channel,
                            money=Money(amount=Decimal(variant.price), currency=CHANNEL_CURRENCY),
                        ),
                    ),
                )
                stock.set_quantity(variant.sku, StockQuantity(variant.stock))

            categories.replace(product.code, (CategorySlug(CATEGORY_CHILD),))
            # Publish so the product is visible on the public storefront.
            products.set_published(product.code, True)

    @staticmethod
    def _seed_collection() -> None:
        if not CollectionModel.objects.filter(slug=COLLECTION_SLUG).exists():
            DjangoCollectionRepository().add(
                Collection(slug=CollectionSlug(COLLECTION_SLUG), name="Featured")
            )
        DjangoCollectionProductRepository().replace(
            COLLECTION_SLUG,
            tuple(ProductCode(product.code) for product in PRODUCTS[:2]),
        )
