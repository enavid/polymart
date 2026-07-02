"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { ProductThumb } from "@/components/storefront/product-thumb";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listStorefrontProducts } from "@/lib/api/catalog";

/** Number of products shown in the "featured" strip on the landing page. */
const FEATURED_LIMIT = 3;

/** The public landing page: a brand hero with a shop CTA and a featured strip. */
export function HomeLanding() {
  const t = useTranslations("home");
  const tStore = useTranslations("storefront");

  const query = useQuery({
    queryKey: ["storefront-featured", FEATURED_LIMIT],
    queryFn: () => listStorefrontProducts({ limit: FEATURED_LIMIT }),
  });

  const products = query.data?.results ?? [];

  return (
    <div className="flex flex-col gap-14">
      <section className="grid items-stretch gap-6 overflow-hidden rounded-2xl border border-border bg-card shadow-sm md:grid-cols-2">
        <div className="flex flex-col items-start justify-center gap-5 px-8 py-12 md:px-10">
          <h1 className="text-4xl font-bold leading-tight tracking-tight md:text-5xl">
            {t("heroTitle")}
          </h1>
          <p className="max-w-prose text-lg text-muted-foreground">{t("heroSubtitle")}</p>
          <Link href="/products" className={buttonVariants({ size: "lg" })}>
            {t("shopCta")}
          </Link>
        </div>
        {/* Warm branded visual panel; decorative, so it stays out of the a11y tree. */}
        <div
          aria-hidden
          className="hidden min-h-56 bg-[image:linear-gradient(135deg,var(--hero-from),var(--hero-to))] md:block"
        />
      </section>

      <section className="flex flex-col gap-6">
        <h2 className="text-2xl font-semibold tracking-tight">{t("featuredTitle")}</h2>

        {query.data && products.length === 0 ? (
          <p className="text-muted-foreground">{t("featuredEmpty")}</p>
        ) : null}

        {products.length > 0 ? (
          <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3">
            {products.map((product) => (
              <Card
                key={product.code}
                className="overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:shadow-md"
              >
                <ProductThumb name={product.name} image={product.image} />
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{product.name}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2 pb-6">
                  <span className="text-sm text-muted-foreground">{product.code}</span>
                  <Link
                    href={`/products/${product.code}`}
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    {tStore("viewProduct")}
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
