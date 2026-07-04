"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ProductCard } from "@/components/storefront/product-card";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  listStorefrontCategories,
  listStorefrontCollections,
  listStorefrontProducts,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

const limit = 12;

/** Rial-per-Toman: the storefront quotes Toman but the ledger unit is the Rial. */
const RIAL_PER_TOMAN = 10;

interface AppliedFilters {
  search: string;
  category: string;
  collection: string;
  min_price: string;
  max_price: string;
  offset: number;
}

const EMPTY_APPLIED: AppliedFilters = {
  search: "",
  category: "",
  collection: "",
  min_price: "",
  max_price: "",
  offset: 0,
};

/** Convert a Toman amount typed by the shopper into the Rial ledger string, or
 *  undefined when the field is blank / not a number. */
function tomanToRial(toman: string): string | undefined {
  const trimmed = toman.trim();
  if (trimmed === "") {
    return undefined;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) && value >= 0 ? String(value * RIAL_PER_TOMAN) : undefined;
}

export function StorefrontProductList() {
  const t = useTranslations("storefront");
  const tCommon = useTranslations("common");

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [collection, setCollection] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [applied, setApplied] = useState<AppliedFilters>(EMPTY_APPLIED);

  const query = useQuery({
    queryKey: ["storefront-products", applied],
    queryFn: () =>
      listStorefrontProducts({
        search: applied.search || undefined,
        category: applied.category || undefined,
        collection: applied.collection || undefined,
        min_price: tomanToRial(applied.min_price),
        max_price: tomanToRial(applied.max_price),
        channel: STOREFRONT_CHANNEL,
        limit,
        offset: applied.offset,
      }),
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

  function applyFilters() {
    setApplied({
      search,
      category,
      collection,
      min_price: minPrice,
      max_price: maxPrice,
      offset: 0,
    });
  }

  function clearFilters() {
    setSearch("");
    setCategory("");
    setCollection("");
    setMinPrice("");
    setMaxPrice("");
    setApplied(EMPTY_APPLIED);
  }

  function goToPage(page: number) {
    setApplied((prev) => ({ ...prev, offset: (page - 1) * limit }));
  }

  const page = query.data;
  const results = page?.results ?? [];
  const currentPage = Math.floor(applied.offset / limit) + 1;
  const pageCount = page ? Math.max(1, Math.ceil(page.count / limit)) : 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
        {/* Search is its own bar, distinct from the sidebar filters. */}
        <div className="flex w-full max-w-md items-end gap-2">
          <div className="flex flex-1 flex-col gap-1.5">
            <Label htmlFor="storefront_search">{t("search")}</Label>
            <Input
              id="storefront_search"
              placeholder={t("searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applyFilters();
              }}
            />
          </div>
          <Button type="button" onClick={applyFilters}>
            {t("search")}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        {/* Sidebar filters */}
        <aside className="flex h-fit flex-col gap-5 rounded-xl border border-border bg-card p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-foreground">{t("filtersTitle")}</h2>

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

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm text-muted-foreground">{t("priceRange")}</legend>
            <div className="flex items-center gap-2">
              <Input
                aria-label={t("priceMin")}
                inputMode="numeric"
                placeholder={t("priceMin")}
                value={minPrice}
                onChange={(e) => setMinPrice(e.target.value)}
              />
              <span aria-hidden className="text-muted-foreground">
                –
              </span>
              <Input
                aria-label={t("priceMax")}
                inputMode="numeric"
                placeholder={t("priceMax")}
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
              />
            </div>
          </fieldset>

          <div className="flex flex-col gap-2">
            <Button type="button" onClick={applyFilters}>
              {t("applyFilters")}
            </Button>
            <Button type="button" variant="ghost" onClick={clearFilters}>
              {t("clearFilters")}
            </Button>
          </div>
        </aside>

        {/* Results */}
        <div className="flex flex-col gap-5">
          {query.isLoading ? <p>{tCommon("loading")}</p> : null}

          {query.isError ? (
            <Alert variant="destructive">
              {query.error instanceof ApiError ? query.error.detail : tCommon("genericError")}
            </Alert>
          ) : null}

          {page ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                <p className="text-sm text-muted-foreground">
                  {t("resultCount", { count: page.count })}
                </p>
                {page.count > 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {t("pageStatus", { page: currentPage, pages: pageCount })}
                  </p>
                ) : null}
              </div>

              {results.length === 0 ? (
                <p className="text-muted-foreground">{t("empty")}</p>
              ) : (
                <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {results.map((product) => (
                    <ProductCard key={product.code} product={product} />
                  ))}
                </div>
              )}

              {pageCount > 1 ? (
                <Pagination
                  currentPage={currentPage}
                  pageCount={pageCount}
                  onGoTo={goToPage}
                  previousLabel={t("previous")}
                  nextLabel={t("next")}
                />
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

interface PaginationProps {
  currentPage: number;
  pageCount: number;
  onGoTo: (page: number) => void;
  previousLabel: string;
  nextLabel: string;
}

/** Numbered pagination with prev/next; shows a compact window around the current
 *  page so the shopper always knows where they are in the list. */
function Pagination({
  currentPage,
  pageCount,
  onGoTo,
  previousLabel,
  nextLabel,
}: PaginationProps) {
  // A window of up to five page numbers centred on the current page.
  const windowSize = 5;
  const half = Math.floor(windowSize / 2);
  let start = Math.max(1, currentPage - half);
  const end = Math.min(pageCount, start + windowSize - 1);
  start = Math.max(1, end - windowSize + 1);
  const pages = Array.from({ length: end - start + 1 }, (_, i) => start + i);

  return (
    <nav className="mt-2 flex items-center justify-center gap-1.5" aria-label="pagination">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onGoTo(currentPage - 1)}
        disabled={currentPage === 1}
      >
        {previousLabel}
      </Button>
      {pages.map((p) => (
        <Button
          key={p}
          type="button"
          variant={p === currentPage ? "default" : "outline"}
          size="sm"
          aria-current={p === currentPage ? "page" : undefined}
          onClick={() => onGoTo(p)}
        >
          {new Intl.NumberFormat("fa-IR").format(p)}
        </Button>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onGoTo(currentPage + 1)}
        disabled={currentPage === pageCount}
      >
        {nextLabel}
      </Button>
    </nav>
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
