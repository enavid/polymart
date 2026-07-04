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
    MediaAsset,
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


# Ten niches x ten products = ~100 products. Names are plain Persian retail names;
# each product's demo photo comes from its niche's curated image pool (see below).
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

# Curated, on-theme demo photos per niche (verified Unsplash IDs). Each product
# draws one from its niche's pool by index, so a category reads as a coherent set
# of real, professional product shots and no two adjacent cards share an image.
# These are stable CDN URLs (Unsplash permits hot-linking); no API key is needed.
_NICHE_IMAGE_IDS: dict[str, tuple[str, ...]] = {
    "elec": (
        "photo-1505740420928-5e560c06d30e",
        "photo-1484704849700-f032a568e944",
        "photo-1608043152269-423dbba4e7e1",
        "photo-1587829741301-dc798b83add3",
        "photo-1527814050087-3793815479db",
        "photo-1523275335684-37898b6baf30",
        "photo-1546868871-7041f2a55e12",
        "photo-1526170375885-4d8ecf77b99f",
    ),
    "aprl": (
        "photo-1521572163474-6864f9cf17ab",
        "photo-1542272604-787c3835535d",
        "photo-1560769629-975ec94e6a86",
        "photo-1434389677669-e08b4cac3105",
        "photo-1576871337622-98d48d1cf531",
        "photo-1620799140408-edc6dcb6d633",
        "photo-1489987707025-afc232f7ea0f",
    ),
    "home": (
        "photo-1556911220-bff31c812dba",
        "photo-1590794056226-79ef3a8147e1",
        "photo-1600585152220-90363fe7e115",
        "photo-1583778176476-4a8b02a64c01",
        "photo-1556911073-38141963c9e0",
        "photo-1588854337221-4cf9fa96059c",
        "photo-1594041680534-e8c8cdebd659",
        "photo-1585515320310-259814833e62",
        "photo-1610701596007-11502861dcfa",
    ),
    "bety": (
        "photo-1596462502278-27bfdc403348",
        "photo-1571781926291-c477ebfd024b",
        "photo-1512496015851-a90fb38ba796",
        "photo-1611930022073-b7a4ba5fcccd",
        "photo-1620916566398-39f1143ab7be",
        "photo-1608248543803-ba4f8c70ae0b",
        "photo-1522335789203-aabd1fc54bc9",
    ),
    "book": (
        "photo-1481833761820-0509d3217039",
        "photo-1512820790803-83ca734da794",
        "photo-1524995997946-a1c2e315a42f",
        "photo-1544716278-ca5e3f4abd8c",
        "photo-1497633762265-9d179a990aa6",
    ),
    "sprt": (
        "photo-1571019613454-1cb2f99b2d8b",
        "photo-1517836357463-d25dfeac3438",
        "photo-1534438327276-14e5300c3a48",
        "photo-1518611012118-696072aa579a",
        "photo-1526506118085-60ce8714f8c5",
        "photo-1540497077202-7c8a3999166f",
        "photo-1584735935682-2f2b69dff9d2",
        "photo-1538805060514-97d9cc17730c",
        "photo-1517963879433-6ad2b056d712",
    ),
    "toys": (
        "photo-1587654780291-39c9404d746b",
        "photo-1566576721346-d4a3b4eaeb55",
        "photo-1515488042361-ee00e0ddd4e4",
        "photo-1596461404969-9ae70f2830c1",
        "photo-1545558014-8692077e9b5c",
        "photo-1596464716127-f2a82984de30",
        "photo-1618842676088-c4d48a6a7c9d",
        "photo-1610484826967-09c5720778c7",
        "photo-1558060370-d644479cb6f7",
    ),
    "groc": (
        "photo-1586201375761-83865001e31c",
        "photo-1509358271058-acd22cc93898",
        "photo-1474979266404-7eaacbcd87c5",
        "photo-1556909212-d5b604d0c90d",
        "photo-1518977676601-b53f82aba655",
    ),
    "bevr": (
        "photo-1514432324607-a09d9b4aefdd",
        "photo-1544787219-7f47ccb76574",
        "photo-1497935586351-b67a49e012bf",
        "photo-1556679343-c7306c1976bc",
        "photo-1461023058943-07fcbe16d735",
    ),
    "offc": (
        "photo-1583485088034-697b5bc54ccd",
        "photo-1531346878377-a5be20888e57",
        "photo-1568205612837-017257d2310a",
        "photo-1519682337058-a94d519337bc",
        "photo-1524578271613-d550eacf6090",
    ),
}

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
    image_url: str
    variants: tuple[_Variant, ...]


# Unsplash CDN, resized/optimized to a card-friendly size on the fly.
_IMAGE_HOST = "https://images.unsplash.com"
_IMAGE_PARAMS = "w=800&q=80&auto=format&fit=crop"


def _image_url(niche_code: str, index: int) -> str:
    """A stable, on-theme photo URL for the ``index``-th product of a niche.

    The image is chosen from the niche's curated pool by index, so it is
    deterministic across re-seeds and neighbouring products never collide.
    """
    pool = _NICHE_IMAGE_IDS[niche_code]
    return f"{_IMAGE_HOST}/{pool[index % len(pool)]}?{_IMAGE_PARAMS}"


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
            code = f"{niche.code}-{i:02d}"
            products.append(
                _Product(
                    code=code,
                    name=name,
                    type_code=niche.code,
                    category=niche.child_slug,
                    description=f"{name} — کیفیت مناسب از دستهٔ {niche.type_name} با قیمت رقابتی.",
                    image_url=_image_url(niche.code, i),
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
            for position, variant in enumerate(product.variants):
                if not ProductVariantModel.objects.filter(sku=variant.sku).exists():
                    # Attach the product photo to its first variant (lowest SKU); the
                    # storefront promotes that as the product's primary image.
                    media = (
                        (MediaAsset(url=product.image_url, alt_text=product.name),)
                        if position == 0
                        else ()
                    )
                    variants.add(
                        ProductVariant(
                            product=ProductCode(product.code),
                            sku=Sku(variant.sku),
                            name=variant.name,
                            media=media,
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
