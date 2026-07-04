"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Loading } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createVariant,
  getProduct,
  getProductCategories,
  listCategories,
  listProductVariants,
  setProductCategories,
  setProductPublished,
  type AttributeValue,
  type Product,
  type VariantMedia,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

function errorMessage(
  mutationError: unknown,
  isError: boolean,
  t: ReturnType<typeof useTranslations>,
  tCommon: ReturnType<typeof useTranslations>,
): string | null {
  if (mutationError instanceof ApiError) {
    return mutationError.status === 409
      ? t("alreadyExists")
      : mutationError.status === 400
        ? t("invalidInput")
        : mutationError.status === 403
          ? t("forbidden")
          : mutationError.detail;
  }
  if (isError) {
    return tCommon("genericError");
  }
  return null;
}

/** A card whose body collapses behind a chevron header, so the side panels can
 *  be folded away to keep the editor compact. */
function CollapsibleCard({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card>
      <CardHeader className="p-0">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex w-full items-center justify-between gap-3 px-6 py-5 text-start"
        >
          <CardTitle>{title}</CardTitle>
          <ChevronDown
            aria-hidden
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              open ? "" : "-rotate-90",
            )}
          />
        </button>
      </CardHeader>
      {open ? <CardContent>{children}</CardContent> : null}
    </Card>
  );
}

/** A labelled read-only fact, stacked (label above value) so several sit side by
 *  side in the horizontal summary row. */
function SummaryField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

/** Product summary: identity, a compact publish toggle beside the status badge,
 *  and attribute values / metadata rendered as labelled rows (never `key = value`). */
function InfoCard({ product }: { product: Product }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const publish = useMutation({
    mutationFn: () => setProductPublished(product.code, !product.is_published),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["product", product.code] });
    },
  });
  const publishError = errorMessage(publish.error, publish.isError, t, tCommon);

  const metadata = Object.entries(product.metadata);

  return (
    <CollapsibleCard title={t("productDetail.info")}>
      <div className="flex flex-col gap-4">
        {/* Facts sit in a horizontal row so the card stays short and wide. */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryField label={t("name")} value={product.name} />
          <SummaryField label={t("code")} value={product.code} />
          <SummaryField label={t("products.productType")} value={product.product_type} />
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{t("products.status")}</span>
            <div className="flex items-center gap-2">
              <Badge variant={product.is_published ? "active" : "inactive"}>
                {product.is_published ? t("products.published") : t("products.draft")}
              </Badge>
              <Button
                size="sm"
                variant="outline"
                onClick={() => publish.mutate()}
                disabled={publish.isPending}
              >
                {publish.isPending
                  ? tCommon("loading")
                  : product.is_published
                    ? t("productDetail.unpublish")
                    : t("productDetail.publish")}
              </Button>
            </div>
          </div>
        </div>

        {publishError ? <Alert variant="destructive">{publishError}</Alert> : null}

        {product.values.length > 0 ? (
          <div className="flex flex-col gap-2 border-t border-border pt-4">
            <p className="text-xs font-medium text-muted-foreground">{t("products.values")}</p>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {product.values.map((value) => (
                <div key={value.attribute} className="flex flex-col gap-0.5 text-sm">
                  <dt className="text-muted-foreground">{value.attribute}</dt>
                  <dd className="font-medium">{value.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}

        {metadata.length > 0 ? (
          <div className="flex flex-col gap-2 border-t border-border pt-4">
            <p className="text-xs font-medium text-muted-foreground">{t("products.metadata")}</p>
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {metadata.map(([key, value]) => (
                <div key={key} className="flex flex-col gap-0.5 text-sm">
                  <dt className="text-muted-foreground">{key}</dt>
                  <dd className="font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
      </div>
    </CollapsibleCard>
  );
}

/** Category membership editor: a checkbox chooser over the existing categories,
 *  so staff pick from a list instead of typing comma-separated slugs. */
function CategoriesCard({ code }: { code: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const all = useQuery({ queryKey: ["catalog-categories"], queryFn: listCategories });
  const current = useQuery({
    queryKey: ["product-categories", code],
    queryFn: () => getProductCategories(code),
  });

  useEffect(() => {
    if (current.data) {
      setSelected(new Set(current.data));
    }
  }, [current.data]);

  const mutation = useMutation({
    mutationFn: () => setProductCategories(code, [...selected]),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["product-categories", code] });
    },
  });

  function toggle(slug: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) {
        next.delete(slug);
      } else {
        next.add(slug);
      }
      return next;
    });
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);
  const categories = all.data ?? [];

  return (
    <CollapsibleCard title={t("productDetail.categories")}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <p className="text-xs text-muted-foreground">{t("productDetail.categoriesChoose")}</p>

          {categories.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("productDetail.categoriesEmpty")}</p>
          ) : (
            <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {categories.map((category) => (
                <li key={category.slug}>
                  <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-primary"
                      checked={selected.has(category.slug)}
                      onChange={() => toggle(category.slug)}
                    />
                    <span>{category.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}

          {mutation.isSuccess ? <Alert variant="success">{t("saved")}</Alert> : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <div>
            <Button type="submit" disabled={mutation.isPending || categories.length === 0}>
              {mutation.isPending ? tCommon("loading") : t("save")}
            </Button>
          </div>
      </form>
    </CollapsibleCard>
  );
}

function VariantsCard({ code }: { code: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [options, setOptions] = useState<AttributeValue[]>([]);
  const [media, setMedia] = useState<VariantMedia[]>([]);

  const query = useQuery({
    queryKey: ["product-variants", code],
    queryFn: () => listProductVariants(code),
  });

  const mutation = useMutation({
    mutationFn: () =>
      createVariant(code, {
        sku,
        name,
        values: options.filter((option) => option.attribute.trim().length > 0),
        media: media.filter((asset) => asset.url.trim().length > 0),
      }),
    onSuccess: () => {
      setSku("");
      setName("");
      setOptions([]);
      setMedia([]);
      setShowAdd(false);
      void queryClient.invalidateQueries({ queryKey: ["product-variants", code] });
    },
  });

  function updateOption(index: number, patch: Partial<AttributeValue>) {
    setOptions((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function updateMedia(index: number, patch: Partial<VariantMedia>) {
    setMedia((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>{t("productDetail.variants")}</CardTitle>
        <Button
          type="button"
          size="sm"
          variant={showAdd ? "outline" : "default"}
          onClick={() => setShowAdd((open) => !open)}
          aria-expanded={showAdd}
        >
          <Plus aria-hidden className="h-4 w-4" />
          {t("productDetail.addVariant")}
        </Button>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {query.isLoading ? <Loading label={tCommon("loading")} /> : null}

          {query.data && query.data.length === 0 ? (
            <p className="text-muted-foreground">{t("productDetail.noVariants")}</p>
          ) : null}

          {query.data && query.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("productDetail.sku")}</TableHead>
                  <TableHead>{t("productDetail.variantName")}</TableHead>
                  <TableHead className="text-end">
                    <span className="sr-only">{t("productDetail.manageVariant")}</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.map((variant) => (
                  <TableRow key={variant.sku} className="transition-colors hover:bg-muted/50">
                    <TableCell className="font-medium">{variant.sku}</TableCell>
                    <TableCell>{variant.name}</TableCell>
                    <TableCell className="text-end">
                      <Link
                        href={`/manage/catalog/variants/${variant.sku}`}
                        className="text-sm font-medium text-primary hover:underline"
                      >
                        {t("productDetail.manageVariant")}
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}

          {showAdd ? (
            <form
              onSubmit={onSubmit}
              className="flex flex-col gap-4 rounded-xl border border-border p-4"
              noValidate
            >
              <p className="text-sm font-medium">{t("productDetail.addVariantForm")}</p>
              <div className="grid gap-4 md:grid-cols-2">
                <FormField
                  id="variant_sku"
                  label={t("productDetail.sku")}
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  required
                />
                <FormField
                  id="variant_name"
                  label={t("productDetail.variantName")}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              <div className="flex flex-col gap-3">
                <p className="text-sm font-medium">{t("productDetail.options")}</p>
                <p className="text-xs text-muted-foreground">{t("productDetail.optionsHint")}</p>
                {options.map((option, index) => (
                  <div key={index} className="grid gap-4 md:grid-cols-2 md:items-end">
                    <FormField
                      id={`variant_option_attribute_${index}`}
                      label={t("productDetail.optionAttribute")}
                      value={option.attribute}
                      onChange={(e) => updateOption(index, { attribute: e.target.value })}
                    />
                    <div className="flex items-end gap-2">
                      <FormField
                        id={`variant_option_value_${index}`}
                        label={t("productDetail.optionValue")}
                        value={option.value}
                        onChange={(e) => updateOption(index, { value: e.target.value })}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setOptions((c) => c.filter((_, i) => i !== index))}
                      >
                        {t("remove")}
                      </Button>
                    </div>
                  </div>
                ))}
                <div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setOptions((c) => [...c, { attribute: "", value: "" }])}
                  >
                    <Plus aria-hidden className="h-4 w-4" />
                    {t("productDetail.addOption")}
                  </Button>
                </div>
              </div>

              <div className="flex flex-col gap-3">
                <p className="text-sm font-medium">{t("productDetail.media")}</p>
                {media.map((asset, index) => (
                  <div key={index} className="grid gap-4 md:grid-cols-2 md:items-end">
                    <FormField
                      id={`variant_media_url_${index}`}
                      label={t("productDetail.mediaUrl")}
                      value={asset.url}
                      onChange={(e) => updateMedia(index, { url: e.target.value })}
                    />
                    <div className="flex items-end gap-2">
                      <FormField
                        id={`variant_media_alt_${index}`}
                        label={t("productDetail.mediaAlt")}
                        value={asset.alt_text}
                        onChange={(e) => updateMedia(index, { alt_text: e.target.value })}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setMedia((c) => c.filter((_, i) => i !== index))}
                      >
                        {t("remove")}
                      </Button>
                    </div>
                  </div>
                ))}
                <div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setMedia((c) => [...c, { url: "", alt_text: "" }])}
                  >
                    <Plus aria-hidden className="h-4 w-4" />
                    {t("productDetail.addMedia")}
                  </Button>
                </div>
              </div>

              {error ? <Alert variant="destructive">{error}</Alert> : null}
              <div className="flex justify-end gap-2 border-t border-border pt-4">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setShowAdd(false)}
                  disabled={mutation.isPending}
                >
                  {tCommon("cancel")}
                </Button>
                <Button type="submit" disabled={mutation.isPending}>
                  {mutation.isPending ? tCommon("loading") : t("productDetail.addVariant")}
                </Button>
              </div>
            </form>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function ProductDetail({ code }: { code: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: ["product", code],
    queryFn: () => getProduct(code),
  });

  return (
    <div className="flex flex-col gap-6">
      {query.isLoading ? <Loading label={tCommon("loading")} /> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data ? (
        <>
          {/* Back-to-products lives in the admin top bar (the section title turns
              into a back link on nested pages); here we only name the product. */}
          <h1 className="text-2xl font-bold tracking-tight">{query.data.name}</h1>
          {/* Full-width horizontal sections stacked top to bottom: a short, wide
              summary; the variants; then the category chooser. This avoids the
              tall-narrow side column that left a big empty gap beside a short
              variants table. */}
          <InfoCard product={query.data} />
          <VariantsCard code={code} />
          <CategoriesCard code={code} />
        </>
      ) : null}
    </div>
  );
}
