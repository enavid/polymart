"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { listStorefrontProducts } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

const limit = 12;

interface AppliedFilters {
  search: string;
  category: string;
  collection: string;
  product_type: string;
  offset: number;
}

const EMPTY_APPLIED: AppliedFilters = {
  search: "",
  category: "",
  collection: "",
  product_type: "",
  offset: 0,
};

export function StorefrontProductList() {
  const t = useTranslations("storefront");
  const tCommon = useTranslations("common");

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [collection, setCollection] = useState("");
  const [productType, setProductType] = useState("");
  const [applied, setApplied] = useState<AppliedFilters>(EMPTY_APPLIED);

  const query = useQuery({
    queryKey: ["storefront-products", applied],
    queryFn: () => listStorefrontProducts({ ...applied, limit }),
  });

  function onSearch() {
    setApplied({
      search,
      category,
      collection,
      product_type: productType,
      offset: 0,
    });
  }

  function goPrevious() {
    setApplied((prev) => ({ ...prev, offset: prev.offset - limit }));
  }

  function goNext() {
    setApplied((prev) => ({ ...prev, offset: prev.offset + limit }));
  }

  const page = query.data;
  const results = page?.results ?? [];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      <div className="grid gap-4 md:grid-cols-4">
        <FormField
          id="storefront_search"
          label={t("search")}
          placeholder={t("searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <FormField
          id="storefront_category"
          label={t("filterCategory")}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <FormField
          id="storefront_collection"
          label={t("filterCollection")}
          value={collection}
          onChange={(e) => setCollection(e.target.value)}
        />
        <FormField
          id="storefront_product_type"
          label={t("filterProductType")}
          value={productType}
          onChange={(e) => setProductType(e.target.value)}
        />
        <div className="md:col-span-4">
          <Button type="button" onClick={onSearch}>
            {t("search")}
          </Button>
        </div>
      </div>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {page ? (
        <>
          <p className="text-sm text-muted-foreground">
            {t("resultCount", { count: page.count })}
          </p>

          {results.length === 0 ? (
            <p className="text-muted-foreground">{t("empty")}</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              {results.map((product) => (
                <Card key={product.code}>
                  <CardHeader>
                    <CardTitle>{product.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    <span className="text-sm text-muted-foreground">
                      {product.code}
                    </span>
                    <Link
                      href={`/products/${product.code}`}
                      className="text-sm font-medium text-primary hover:underline"
                    >
                      {t("viewProduct")}
                    </Link>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={goPrevious}
              disabled={applied.offset === 0}
            >
              {t("previous")}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={goNext}
              disabled={applied.offset + limit >= page.count}
            >
              {t("next")}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
