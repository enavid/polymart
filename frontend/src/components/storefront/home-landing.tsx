"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { CategoryShortcuts } from "@/components/storefront/category-shortcuts";
import { ProductCard } from "@/components/storefront/product-card";
import { ProductRow } from "@/components/storefront/product-row";
import { ProductThumb } from "@/components/storefront/product-thumb";
import { TrustBadges } from "@/components/storefront/trust-badges";
import {
  listStorefrontCategories,
  listStorefrontProducts,
  type StorefrontCategory,
  type StorefrontProduct,
} from "@/lib/api/catalog";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

/** Number of products pulled for each strip (curated and per-category). */
const FEATURED_LIMIT = 12;

/** How many curated products the featured grid shows at once. */
const FEATURED_GRID = 8;

/** How many top-level categories get their own product strip on the landing. */
const CATEGORY_ROWS = 6;

/** How many featured photos flank the hero on wide screens. */
const HERO_IMAGES = 3;

/**
 * The slug of the admin-curated "featured" collection. Staff choose the showcase
 * by adding products to this collection in the catalog admin; the storefront just
 * reads its members. When it is empty (or absent) the landing falls back to a
 * plain product listing so the strip is never blank.
 */
const FEATURED_COLLECTION = "featured";

/** The public landing page: a brand hero with a live product collage, a trust
 *  strip, quick category shortcuts, a curated grid, a call-to-action band, and
 *  one strip per top-level category -- a dense, varied storefront rather than a
 *  stack of identical rows. */
export function HomeLanding() {
  const t = useTranslations("home");

  const categories = useQuery({
    queryKey: ["storefront-categories"],
    queryFn: listStorefrontCategories,
  });

  // Only top-level categories get a shortcut tile and their own strip; child
  // categories stay reachable through the listing's filters.
  const topCategories = (categories.data ?? []).filter((c) => c.parent === null);

  const curated = useQuery({
    queryKey: ["storefront-featured", STOREFRONT_CHANNEL],
    queryFn: () =>
      listStorefrontProducts({
        collection: FEATURED_COLLECTION,
        channel: STOREFRONT_CHANNEL,
        limit: FEATURED_LIMIT,
      }),
  });

  // Only fall back to a general listing once we know the curated collection is empty.
  const curatedEmpty = curated.isSuccess && curated.data.results.length === 0;
  const fallback = useQuery({
    queryKey: ["storefront-featured-fallback", STOREFRONT_CHANNEL],
    enabled: curatedEmpty,
    queryFn: () =>
      listStorefrontProducts({ channel: STOREFRONT_CHANNEL, limit: FEATURED_LIMIT }),
  });

  const products = curatedEmpty
    ? (fallback.data?.results ?? [])
    : (curated.data?.results ?? []);
  const resolved = curated.isSuccess && (!curatedEmpty || fallback.isSuccess);

  // Products already on the curated grid are dropped from the per-category strips
  // so the same card never appears twice on one screen.
  const featuredCodes = new Set(products.map((p) => p.code));

  // Real product photos give the hero an e-commerce feel; skip it rather than
  // show monogram placeholders when the featured set has no imagery.
  const heroImages = products.filter((p) => p.image).slice(0, HERO_IMAGES);

  return (
    <div className="flex flex-col gap-10">
      {/* Two-column hero: the pitch on the start side, a live collage of curated
          product photos on the end (wide screens only). */}
      <section className="overflow-hidden rounded-2xl bg-[image:linear-gradient(135deg,var(--hero-from),var(--hero-to))] text-white shadow-sm">
        <div className="grid gap-8 px-6 py-10 sm:px-10 md:py-14 lg:grid-cols-2 lg:items-center">
          <div className="flex flex-col items-start gap-4">
            <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-medium">
              {t("heroEyebrow")}
            </span>
            <h1 className="text-3xl font-bold leading-tight tracking-tight md:text-4xl">
              {t("heroTitle")}
            </h1>
            <p className="text-lg text-white/85">{t("heroSubtitle")}</p>
            <Link
              href="/products"
              className="mt-1 inline-flex h-11 items-center justify-center rounded-md bg-white px-6 text-sm font-semibold text-primary shadow-sm transition-colors hover:bg-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
            >
              {t("shopCta")}
            </Link>
          </div>

          {heroImages.length >= 2 ? <HeroCollage products={heroImages} /> : null}
        </div>
      </section>

      {/* Reassurance sits high, where it can actually reassure before the scroll. */}
      <TrustBadges />

      <CategoryShortcuts categories={topCategories} />

      {/* Curated grid: shows many products at once instead of hiding them behind a
          swipe, and it does not auto-rotate. */}
      <section className="flex flex-col gap-5">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
              {t("featuredTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">{t("featuredSubtitle")}</p>
          </div>
          <Link href="/products" className="shrink-0 text-sm font-medium text-primary hover:underline">
            {t("viewAll")}
          </Link>
        </div>

        {resolved && products.length === 0 ? (
          <p className="text-muted-foreground">{t("featuredEmpty")}</p>
        ) : null}

        {products.length > 0 ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {products.slice(0, FEATURED_GRID).map((product) => (
              <ProductCard key={product.code} product={product} />
            ))}
          </div>
        ) : null}
      </section>

      {/* A coloured call-to-action band breaks the rhythm and gives the page a
          focal point between the grid and the category strips. */}
      <section className="flex flex-col items-start gap-4 rounded-2xl bg-[image:linear-gradient(135deg,var(--hero-from),var(--hero-to))] px-6 py-8 text-white shadow-sm sm:flex-row sm:items-center sm:justify-between sm:px-10">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-bold tracking-tight sm:text-2xl">{t("ctaTitle")}</h2>
          <p className="text-white/85">{t("ctaSubtitle")}</p>
        </div>
        <Link
          href="/products"
          className="inline-flex h-11 shrink-0 items-center justify-center rounded-md bg-white px-6 text-sm font-semibold text-primary shadow-sm transition-colors hover:bg-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
        >
          {t("ctaButton")}
        </Link>
      </section>

      {topCategories.slice(0, CATEGORY_ROWS).map((category) => (
        <CategoryProductRow key={category.slug} category={category} excludeCodes={featuredCodes} />
      ))}
    </div>
  );
}

/** The hero's product collage: a short stack of overlapping, slightly-rotated
 *  product photos that make the pitch feel like a real shop. Decorative and
 *  wide-screen only. */
function HeroCollage({ products }: { products: StorefrontProduct[] }) {
  return (
    <div aria-hidden className="hidden justify-end gap-3 lg:flex">
      {products.map((product, index) => (
        <div
          key={product.code}
          className="w-32 overflow-hidden rounded-2xl bg-white shadow-lg ring-1 ring-white/40"
          style={{ transform: `rotate(${(index - 1) * 3}deg)` }}
        >
          <ProductThumb name={product.name} image={product.image} />
        </div>
      ))}
    </div>
  );
}

/** One home-page strip for a single category: fetches that category's products
 *  (minus anything already on the curated grid) and renders a titled row, or
 *  nothing when the category has none, so the page only ever shows category rows
 *  that have something to show. */
function CategoryProductRow({
  category,
  excludeCodes,
}: {
  category: StorefrontCategory;
  excludeCodes: Set<string>;
}) {
  const t = useTranslations("home");

  const query = useQuery({
    queryKey: ["storefront-category-row", STOREFRONT_CHANNEL, category.slug],
    queryFn: () =>
      listStorefrontProducts({
        category: category.slug,
        channel: STOREFRONT_CHANNEL,
        limit: FEATURED_LIMIT,
      }),
  });

  const products = (query.data?.results ?? []).filter((p) => !excludeCodes.has(p.code));
  if (products.length === 0) {
    return null;
  }

  return (
    <ProductRow
      title={category.name}
      viewAllHref={`/products?category=${encodeURIComponent(category.slug)}`}
      viewAllLabel={t("viewAll")}
      products={products}
    />
  );
}
