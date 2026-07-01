"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getStorefrontProduct } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

export function StorefrontProductDetail({ code }: { code: string }) {
  const t = useTranslations("storefront");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: ["storefront-product", code],
    queryFn: () => getStorefrontProduct(code),
  });

  let error: string | null = null;
  if (query.error instanceof ApiError) {
    error = query.error.status === 404 ? t("notFound") : query.error.detail;
  } else if (query.isError) {
    error = tCommon("genericError");
  }

  const product = query.data;

  return (
    <div className="flex flex-col gap-6">
      <Link href="/products" className="text-sm text-primary hover:underline">
        {t("backToList")}
      </Link>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {error ? <Alert variant="destructive">{error}</Alert> : null}

      {product ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold">{product.name}</h1>
            <span className="text-sm text-muted-foreground">
              {product.product_type}
            </span>
          </div>

          {product.values.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("attributes")}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {product.values.map((value) => (
                  <div
                    key={value.attribute}
                    className="flex justify-between gap-4 text-sm"
                  >
                    <span className="text-muted-foreground">
                      {value.attribute}
                    </span>
                    <span>{value.value}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {Object.keys(product.metadata).length > 0 ? (
            <dl className="flex flex-col gap-2 text-sm">
              {Object.entries(product.metadata).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
