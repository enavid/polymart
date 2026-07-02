"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ProductThumb } from "@/components/storefront/product-thumb";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Label } from "@/components/ui/label";
import {
  listStorefrontCategories,
  listStorefrontCollections,
  listStorefrontProducts,
  listStorefrontProductTypes,
  type StorefrontProduct,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { formatMoneyString } from "@/lib/format";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

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
    queryFn: () =>
      listStorefrontProducts({ ...applied, channel: STOREFRONT_CHANNEL, limit }),
  });

  // Filter choosers, populated from the public storefront taxonomy endpoints.
  const categories = useQuery({
    queryKey: ["storefront-categories"],
    queryFn: listStorefrontCategories,
  });
  const collections = useQuery({
    queryKey: ["storefront-collections"],
    queryFn: listStorefrontCollections,
  });
  const productTypes = useQuery({
    queryKey: ["storefront-product-types"],
    queryFn: listStorefrontProductTypes,
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
        <FilterSelect
          id="storefront_category"
          label={t("filterCategory")}
          allLabel={t("filterAll")}
          value={category}
          onChange={setCategory}
          options={(categories.data ?? []).map((c) => ({ value: c.slug, label: c.name }))}
        />
        <FilterSelect
          id="storefront_collection"
          label={t("filterCollection")}
          allLabel={t("filterAll")}
          value={collection}
          onChange={setCollection}
          options={(collections.data ?? []).map((c) => ({ value: c.slug, label: c.name }))}
        />
        <FilterSelect
          id="storefront_product_type"
          label={t("filterProductType")}
          allLabel={t("filterAll")}
          value={productType}
          onChange={setProductType}
          options={(productTypes.data ?? []).map((p) => ({ value: p.code, label: p.name }))}
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
            <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3">
              {results.map((product) => (
                <Card
                  key={product.code}
                  className="overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:shadow-md"
                >
                  <ProductThumb name={product.name} image={product.image} />
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{product.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 pb-6">
                    <span className="text-sm text-muted-foreground">
                      {product.code}
                    </span>
                    <ProductCardPrice product={product} />
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

/** The "from" price + availability badge on a PLP card, for the active channel. */
function ProductCardPrice({ product }: { product: StorefrontProduct }) {
  const t = useTranslations("storefront");
  // Pricing fields are present because the list is requested with a channel.
  const price =
    product.from_price != null && product.currency != null
      ? t("priceFrom", { price: formatMoneyString(product.from_price, product.currency) })
      : t("noPrice");

  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm font-medium">{price}</span>
      {product.available === false ? (
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {t("outOfStock")}
        </span>
      ) : null}
    </div>
  );
}

interface FilterSelectProps {
  id: string;
  label: string;
  allLabel: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}

/** A labelled dropdown for a storefront filter; the empty value means "all". */
function FilterSelect({ id, label, allLabel, value, onChange, options }: FilterSelectProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        name={id}
        className="h-10 rounded-md border border-input bg-background px-3 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
