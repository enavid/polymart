"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

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
    <div className="flex flex-col gap-10">
      <section className="flex flex-col items-start gap-4 rounded-lg border border-border bg-accent/40 px-6 py-12">
        <h1 className="text-3xl font-bold">{t("heroTitle")}</h1>
        <p className="text-muted-foreground">{t("heroSubtitle")}</p>
        <Link href="/products" className={buttonVariants()}>
          {t("shopCta")}
        </Link>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold">{t("featuredTitle")}</h2>

        {query.data && products.length === 0 ? (
          <p className="text-muted-foreground">{t("featuredEmpty")}</p>
        ) : null}

        {products.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-3">
            {products.map((product) => (
              <Card key={product.code}>
                <CardHeader>
                  <CardTitle>{product.name}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
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
