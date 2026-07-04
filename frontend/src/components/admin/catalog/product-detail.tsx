"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";

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
  listProductVariants,
  setProductCategories,
  setProductPublished,
  type AttributeValue,
  type Product,
  type VariantMedia,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

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

function InfoCard({ product }: { product: Product }) {
  const t = useTranslations("catalog");

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("productDetail.info")}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-2 text-sm">
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("name")}</dt>
            <dd className="font-medium">{product.name}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("code")}</dt>
            <dd>{product.code}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("products.productType")}</dt>
            <dd>{product.product_type}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("products.status")}</dt>
            <dd>
              <Badge variant={product.is_published ? "active" : "inactive"}>
                {product.is_published
                  ? t("products.published")
                  : t("products.draft")}
              </Badge>
            </dd>
          </div>
        </dl>

        <h3 className="mt-4 text-sm font-medium">{t("products.values")}</h3>
        {product.values.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("none")}</p>
        ) : (
          <ul className="text-sm">
            {product.values.map((value) => (
              <li key={value.attribute}>
                {value.attribute} = {value.value}
              </li>
            ))}
          </ul>
        )}

        {Object.keys(product.metadata).length > 0 ? (
          <ul className="mt-2 text-sm">
            {Object.entries(product.metadata).map(([key, value]) => (
              <li key={key}>
                {key} = {value}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

function PublicationCard({ product }: { product: Product }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => setProductPublished(product.code, !product.is_published),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["product", product.code] });
    },
  });

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("productDetail.publication")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending
              ? tCommon("loading")
              : product.is_published
                ? t("productDetail.unpublish")
                : t("productDetail.publish")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CategoriesCard({ code }: { code: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [categories, setCategories] = useState("");

  const query = useQuery({
    queryKey: ["product-categories", code],
    queryFn: () => getProductCategories(code),
  });

  useEffect(() => {
    if (query.data) {
      setCategories(query.data.join(", "));
    }
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: () =>
      setProductCategories(
        code,
        categories
          .split(",")
          .map((slug) => slug.trim())
          .filter((slug) => slug.length > 0),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["product-categories", code] });
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("productDetail.categories")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <FormField
            id="product_categories"
            label={t("productDetail.categories")}
            hint={t("productDetail.categoriesHint")}
            value={categories}
            onChange={(e) => setCategories(e.target.value)}
          />
          {mutation.isSuccess ? (
            <Alert variant="success">{t("saved")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <div>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? tCommon("loading") : t("save")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function VariantsCard({ code }: { code: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
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
      <CardHeader>
        <CardTitle>{t("productDetail.variants")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {query.isLoading ? <p>{tCommon("loading")}</p> : null}

          {query.data && query.data.length === 0 ? (
            <p className="text-muted-foreground">{t("productDetail.noVariants")}</p>
          ) : null}

          {query.data && query.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("productDetail.sku")}</TableHead>
                  <TableHead>{t("productDetail.variantName")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.map((variant) => (
                  <TableRow key={variant.sku}>
                    <TableCell className="font-medium">{variant.sku}</TableCell>
                    <TableCell>{variant.name}</TableCell>
                    <TableCell>
                      <Link href={`/manage/catalog/variants/${variant.sku}`}>
                        {t("productDetail.manageVariant")}
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}

          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
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
                  {t("productDetail.addMedia")}
                </Button>
              </div>
            </div>

            {error ? <Alert variant="destructive">{error}</Alert> : null}
            <div>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? tCommon("loading") : t("productDetail.addVariant")}
              </Button>
            </div>
          </form>
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
      <Link href="/manage/catalog/products" className="text-sm text-muted-foreground">
        {t("productDetail.backToProducts")}
      </Link>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data ? (
        <>
          <h1 className="text-xl font-semibold">{query.data.name}</h1>
          <InfoCard product={query.data} />
          <PublicationCard product={query.data} />
          <CategoriesCard code={code} />
          <VariantsCard code={code} />
        </>
      ) : null}
    </div>
  );
}
