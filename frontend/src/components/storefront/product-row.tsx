"use client";

import Link from "next/link";

import { FeaturedCarousel } from "@/components/storefront/featured-carousel";
import type { StorefrontProduct } from "@/lib/api/catalog";

/**
 * A titled horizontal strip of products: a heading with an optional subtitle, a
 * "view all" link to the filtered listing, and a swipeable carousel of cards.
 *
 * This is the home page's repeating building block (the curated strip plus one
 * strip per top-level category). It is purely presentational -- the caller owns
 * fetching and simply omits the row when it has no products, so a row is never
 * rendered empty. The carousel does not auto-rotate here: several rows advancing
 * at once would fight for the reader's attention.
 */
export function ProductRow({
  title,
  subtitle,
  viewAllHref,
  viewAllLabel,
  products,
}: {
  title: string;
  subtitle?: string;
  viewAllHref: string;
  viewAllLabel: string;
  products: StorefrontProduct[];
}) {
  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h2>
          {subtitle ? <p className="text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>
        <Link
          href={viewAllHref}
          className="shrink-0 text-sm font-medium text-primary hover:underline"
        >
          {viewAllLabel}
        </Link>
      </div>
      <FeaturedCarousel products={products} autoAdvance={false} />
    </section>
  );
}
