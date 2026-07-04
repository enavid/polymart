"""Seed a large, varied demo catalog for local exploration.

Unlike ``seed_e2e`` (a tiny, locked fixture the Playwright suite asserts against),
this command fills a dev database with a rich, realistic dataset -- many product
types across different niches (electronics, apparel, home, beauty, books, ...),
around a hundred published products with per-channel prices and stock, a category
tree, and a few collections -- so the storefront and admin panel can be explored
with data that actually looks like a real store.

It is **idempotent** (safe to re-run) and, like ``seed_e2e``, refuses to run
outside DEBUG so it can never touch a production database. It shares the main
sales channel with ``seed_e2e`` but uses its own product types, categories,
collections, and product/SKU codes, so the two seeds never collide.
"""
# This file is Persian demo data: RUF001 flags Persian letters/digits as
# "confusable" with Latin look-alikes, which is a false positive for genuine
# Persian text. Disable it here rather than annotating every retail name.
# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

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

logger = structlog.get_logger(__name__)

# Shared with seed_e2e (both just ensure it exists); the storefront reads it.
CHANNEL_SLUG = "ir-main"
CHANNEL_CURRENCY = "IRR"


@dataclass(frozen=True)
class _Niche:
    """A product family: its own product type, a root→child category, and products."""

    code: str  # lowercase slug stem for product codes + product-type code
    prefix: str  # uppercase stem for SKUs
    type_name: str
    root_slug: str
    root_name: str
    child_slug: str
    child_name: str
    products: tuple[str, ...]  # Persian display names


# Ten niches x ten products = ~100 products. Names are plain Persian retail names.
NICHES: tuple[_Niche, ...] = (
    _Niche(
        "elec",
        "ELEC",
        "الکترونیک",
        "electronics",
        "الکترونیک",
        "gadgets",
        "گجت‌ها",
        (
            "هدفون بی‌سیم",
            "اسپیکر بلوتوثی",
            "شارژر سریع",
            "پاوربانک ۲۰۰۰۰",
            "کیبورد مکانیکی",
            "ماوس گیمینگ",
            "وب‌کم HD",
            "هاب USB-C",
            "ساعت هوشمند",
            "دستبند سلامت",
        ),
    ),
    _Niche(
        "aprl",
        "APRL",
        "پوشاک",
        "fashion",
        "مد و پوشاک",
        "clothing",
        "لباس",
        (
            "تی‌شرت نخی",
            "پیراهن آستین‌بلند",
            "شلوار جین",
            "هودی کلاه‌دار",
            "ژاکت بافت",
            "کاپشن پاییزه",
            "پولوشرت",
            "شلوارک ورزشی",
            "جوراب پک سه‌تایی",
            "کلاه بافتنی",
        ),
    ),
    _Niche(
        "home",
        "HOME",
        "خانه و آشپزخانه",
        "home",
        "خانه",
        "kitchen",
        "آشپزخانه",
        (
            "قابلمه استیل",
            "ماهیتابه نچسب",
            "سرویس بشقاب",
            "لیوان سرامیکی",
            "چاقو آشپزخانه",
            "برد برش چوبی",
            "کتری برقی",
            "آبمیوه‌گیری",
            "ظرف نگهدارنده",
            "دستمال میکروفایبر",
        ),
    ),
    _Niche(
        "bety",
        "BETY",
        "زیبایی و سلامت",
        "beauty",
        "زیبایی و سلامت",
        "skincare",
        "مراقبت پوست",
        (
            "کرم مرطوب‌کننده",
            "ضدآفتاب SPF50",
            "شامپو گیاهی",
            "سرم ویتامین C",
            "ماسک صورت",
            "لوسیون بدن",
            "بالم لب",
            "روغن آرگان",
            "برس مو",
            "ست مانیکور",
        ),
    ),
    _Niche(
        "book",
        "BOOK",
        "کتاب",
        "media",
        "کتاب و رسانه",
        "books",
        "کتاب‌ها",
        (
            "رمان کلاسیک",
            "کتاب کودک مصور",
            "راهنمای برنامه‌نویسی",
            "کتاب آشپزی",
            "دفتر یادداشت",
            "کتاب تاریخ",
            "مجموعه شعر",
            "کتاب روان‌شناسی",
            "اطلس جغرافیا",
            "کتاب هنر",
        ),
    ),
    _Niche(
        "sprt",
        "SPRT",
        "ورزش و تناسب اندام",
        "sports",
        "ورزش",
        "fitness",
        "تناسب اندام",
        (
            "مت یوگا",
            "دمبل ۵ کیلویی",
            "طناب ورزشی",
            "کش مقاومتی",
            "بطری آب ورزشی",
            "کفش دویدن",
            "توپ فوتبال",
            "ساک ورزشی",
            "دستکش تمرین",
            "فوم رولر",
        ),
    ),
    _Niche(
        "toys",
        "TOYS",
        "اسباب‌بازی و کودک",
        "kids",
        "کودک",
        "toys",
        "اسباب‌بازی",
        (
            "بلوک ساختنی",
            "عروسک پارچه‌ای",
            "ماشین کنترلی",
            "پازل ۱۰۰ تکه",
            "قطار چوبی",
            "کتاب رنگ‌آمیزی",
            "ست نقاشی",
            "پازل مکعبی",
            "ربات اسباب‌بازی",
            "خمیر بازی",
        ),
    ),
    _Niche(
        "groc",
        "GROC",
        "خواروبار",
        "grocery",
        "خواروبار",
        "pantry",
        "کالای اساسی",
        (
            "برنج ایرانی",
            "روغن زیتون",
            "عسل طبیعی",
            "زعفران سرگل",
            "چای سیاه",
            "خرمای مضافتی",
            "آجیل مخلوط",
            "رب گوجه",
            "ماکارونی",
            "شکر سفید",
        ),
    ),
    _Niche(
        "bevr",
        "BEVR",
        "نوشیدنی",
        "drinks",
        "نوشیدنی",
        "hotdrinks",
        "نوشیدنی گرم",
        (
            "قهوه اسپرسو",
            "چای سبز",
            "دمنوش گیاهی",
            "شکلات داغ",
            "شربت آلبالو",
            "آب معدنی",
            "نوشابه گازدار",
            "ماته",
            "پودر کاکائو",
            "قهوه فوری",
        ),
    ),
    _Niche(
        "offc",
        "OFFC",
        "لوازم‌التحریر و اداری",
        "office",
        "اداری",
        "stationery",
        "لوازم‌التحریر",
        (
            "خودکار پک ده‌تایی",
            "دفتر یادداشت سیمی",
            "ماژیک هایلایت",
            "مداد رنگی",
            "چسب نواری",
            "منگنه اداری",
            "پوشه پلاستیکی",
            "ماشین‌حساب",
            "تخته وایت‌برد",
            "برچسب یادداشت",
        ),
    ),
)

# A few collections built from deterministic slices of the catalog.
COLLECTION_FEATURED = "demo-featured"
COLLECTION_BESTSELLERS = "demo-bestsellers"
COLLECTION_NEW = "demo-new-arrivals"

_VARIANT_NAMES: dict[int, tuple[str, ...]] = {
    1: ("استاندارد",),
    2: ("معمولی", "بزرگ"),
    3: ("کوچک", "متوسط", "بزرگ"),
}


@dataclass(frozen=True)
class _Variant:
    sku: str
    name: str
    price: str
    stock: int


@dataclass(frozen=True)
class _Product:
    code: str
    name: str
    type_code: str
    category: str
    description: str
    variants: tuple[_Variant, ...]


def build_products() -> tuple[_Product, ...]:
    """Expand the niche definitions into the full, deterministic product catalog.

    Single source of truth shared by the command and its tests. Prices and stock
    are derived from the indices so the dataset is stable across runs; every ~9th
    line is out of stock and product variant counts cycle 1→2→3 so the storefront
    exercises the out-of-stock and variant-picker paths.
    """

    products: list[_Product] = []
    for niche in NICHES:
        for i, name in enumerate(niche.products):
            count = 1 + (i % 3)
            variant_names = _VARIANT_NAMES[count]
            variants = tuple(
                _Variant(
                    sku=f"{niche.prefix}{i:02d}-{chr(ord('A') + v)}",
                    name=variant_names[v],
                    price=f"{niche_base(niche) + i * 15000 + v * 40000}.00",
                    stock=0 if (i + v) % 9 == 0 else 5 + ((i * 3 + v * 7) % 40),
                )
                for v in range(count)
            )
            products.append(
                _Product(
                    code=f"{niche.code}-{i:02d}",
                    name=name,
                    type_code=niche.code,
                    category=niche.child_slug,
                    description=f"{name} — کیفیت مناسب از دستهٔ {niche.type_name} با قیمت رقابتی.",
                    variants=variants,
                )
            )
    return tuple(products)


def niche_base(niche: _Niche) -> int:
    """A per-niche base price (Toman-ish IRR) so different families sit at different tiers."""
    # Stable, order-derived base so prices look intentional without a lookup table.
    return 90000 + (NICHES.index(niche) * 55000)


class Command(BaseCommand):
    help = "Seed a large, varied demo catalog for local exploration (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo refuses to run outside DEBUG -- it is a local dev fixture, "
                "never for a production database."
            )

        products = build_products()
        with transaction.atomic():
            self._seed_channel()
            self._seed_product_types()
            self._seed_categories()
            self._seed_products(products)
            self._seed_collections(products)

        logger.info(
            "demo_seed_completed",
            channel=CHANNEL_SLUG,
            niches=len(NICHES),
            products=len(products),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo seed complete: {len(products)} products across {len(NICHES)} niches."
            )
        )

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

    @staticmethod
    def _seed_product_types() -> None:
        repo = DjangoProductTypeRepository()
        for niche in NICHES:
            if not ProductTypeModel.objects.filter(code=niche.code).exists():
                repo.add(ProductType(code=ProductTypeCode(niche.code), name=niche.type_name))

    @staticmethod
    def _seed_categories() -> None:
        repo = DjangoCategoryRepository()
        for niche in NICHES:
            if not CategoryModel.objects.filter(slug=niche.root_slug).exists():
                repo.add(Category(slug=CategorySlug(niche.root_slug), name=niche.root_name))
            if not CategoryModel.objects.filter(slug=niche.child_slug).exists():
                repo.add(
                    Category(
                        slug=CategorySlug(niche.child_slug),
                        name=niche.child_name,
                        parent=CategorySlug(niche.root_slug),
                    )
                )

    @staticmethod
    def _seed_products(products: tuple[_Product, ...]) -> None:
        product_repo = DjangoProductRepository()
        variants = DjangoVariantRepository()
        prices = DjangoVariantPriceRepository()
        stock = DjangoStockRepository()
        categories = DjangoProductCategoryRepository()

        for product in products:
            if not ProductModel.objects.filter(code=product.code).exists():
                product_repo.add(
                    Product(
                        code=ProductCode(product.code),
                        name=product.name,
                        product_type=ProductTypeCode(product.type_code),
                    )
                )
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
                            channel=CHANNEL_SLUG,
                            money=Money(amount=Decimal(variant.price), currency=CHANNEL_CURRENCY),
                        ),
                    ),
                )
                stock.set_quantity(variant.sku, StockQuantity(variant.stock))

            categories.replace(product.code, (CategorySlug(product.category),))
            product_repo.set_published(product.code, True)

    @staticmethod
    def _seed_collections(products: tuple[_Product, ...]) -> None:
        repo = DjangoCollectionRepository()
        members = DjangoCollectionProductRepository()

        plan: tuple[tuple[str, str, tuple[_Product, ...]], ...] = (
            # One flagship product from each niche (every 10th product).
            (COLLECTION_FEATURED, "منتخب", products[::10]),
            # A deterministic "best sellers" slice.
            (COLLECTION_BESTSELLERS, "پرفروش‌ها", products[3:21:2]),
            # The "newest" tail of the catalog.
            (COLLECTION_NEW, "تازه‌ها", products[-12:]),
        )
        for slug, name, member_products in plan:
            if not CollectionModel.objects.filter(slug=slug).exists():
                repo.add(Collection(slug=CollectionSlug(slug), name=name))
            members.replace(slug, tuple(ProductCode(p.code) for p in member_products))
