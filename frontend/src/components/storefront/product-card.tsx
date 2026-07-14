"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { ProductThumb } from "@/components/storefront/product-thumb";
import { Card } from "@/components/ui/card";
import type { StorefrontProduct } from "@/lib/api/catalog";
import { formatMoneyString, formatPercent } from "@/lib/format";

/**
 * A storefront product card: the whole tile is one link to the product, with the
 * photo as the hero, the name and price as the primary content, and an
 * out-of-stock badge overlaid on the image. The internal product code (an
 * operational identifier) is intentionally never shown to shoppers.
 *
 * Pricing fields are present only when the product was fetched for a channel; on
 * surfaces without a channel (e.g. the landing strip) the price line is omitted
 * rather than rendered as "no price".
 */
export function ProductCard({ product }: { product: StorefrontProduct }) {
  const t = useTranslations("storefront");

  const inChannel = product.currency != null;
  const priced = product.from_price != null && product.currency != null;
  const soldOut = product.available === false;

  return (
    <Link
      href={`/products/${product.code}`}
      className="group block rounded-xl focus-visible:outline-none"
    >
      <Card className="h-full overflow-hidden transition duration-200 group-hover:-translate-y-0.5 group-hover:shadow-md group-focus-visible:ring-2 group-focus-visible:ring-ring">
        <div className="relative">
          <ProductThumb name={product.name} image={product.image} />
          {soldOut ? (
            <span className="absolute end-2 top-2 rounded-full bg-background/90 px-2.5 py-1 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur">
              {t("outOfStock")}
            </span>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5 p-4">
          <h3 className="line-clamp-2 text-sm font-medium leading-snug text-foreground">
            {product.name}
          </h3>
          {priced ? (
            <>
              <p className="text-base font-semibold text-foreground">
                {t("priceFrom", {
                  price: formatMoneyString(product.from_price!, product.currency!),
                })}
              </p>
              {product.tax_rate != null ? (
                <p className="text-xs text-muted-foreground">
                  {t("taxIncluded", { rate: formatPercent(product.tax_rate) })}
                </p>
              ) : null}
            </>
          ) : inChannel ? (
            <p className="text-sm text-muted-foreground">{t("noPrice")}</p>
          ) : null}
        </div>
      </Card>
    </Link>
  );
}
