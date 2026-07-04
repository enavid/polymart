"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { FeaturedCarousel } from "@/components/storefront/featured-carousel";
import { listStorefrontProducts } from "@/lib/api/catalog";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

/** Number of products pulled for the featured strip. */
const FEATURED_LIMIT = 12;

/**
 * The slug of the admin-curated "featured" collection. Staff choose the showcase
 * by adding products to this collection in the catalog admin; the storefront just
 * reads its members. When it is empty (or absent) the landing falls back to a
 * plain product listing so the strip is never blank.
 */
const FEATURED_COLLECTION = "featured";

/** The public landing page: a compact brand hero and an auto-rotating showcase of
 *  admin-curated featured products. */
export function HomeLanding() {
  const t = useTranslations("home");

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

  return (
    <div className="flex flex-col gap-12">
      {/* Compact, horizontal hero -- uses the width, and keeps the featured strip
          reachable without a long scroll. */}
      <section className="overflow-hidden rounded-2xl bg-[image:linear-gradient(135deg,var(--hero-from),var(--hero-to))] text-white shadow-sm">
        <div className="flex flex-col items-start gap-4 px-6 py-10 sm:px-10 md:max-w-2xl md:py-14">
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
      </section>

      <section className="flex flex-col gap-5">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">{t("featuredTitle")}</h2>
            <p className="text-sm text-muted-foreground">{t("featuredSubtitle")}</p>
          </div>
          <Link href="/products" className="text-sm font-medium text-primary hover:underline">
            {t("viewAll")}
          </Link>
        </div>

        {resolved && products.length === 0 ? (
          <p className="text-muted-foreground">{t("featuredEmpty")}</p>
        ) : null}

        {products.length > 0 ? <FeaturedCarousel products={products} /> : null}
      </section>
    </div>
  );
}
