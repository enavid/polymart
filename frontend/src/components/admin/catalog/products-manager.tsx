"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

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
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createProduct,
  listProducts,
  listProductTypes,
  type AttributeValue,
  type Product,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

const PRODUCTS_KEY = "catalog-products";
const PRODUCT_TYPES_KEY = "catalog-product-types";

interface ValueRow {
  attribute: string;
  value: string;
}

function CreateProductForm({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [productType, setProductType] = useState("");
  const [values, setValues] = useState<ValueRow[]>([]);

  const typesQuery = useQuery({
    queryKey: [PRODUCT_TYPES_KEY],
    queryFn: listProductTypes,
  });

  const mutation = useMutation({
    mutationFn: () => {
      const cleaned: AttributeValue[] = values
        .filter((row) => row.attribute.trim() !== "")
        .map((row) => ({ attribute: row.attribute, value: row.value }));
      return createProduct({
        code,
        name,
        product_type: productType,
        values: cleaned,
      });
    },
    onSuccess: () => {
      setCode("");
      setName("");
      setProductType("");
      setValues([]);
      onCreated();
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  function addValue() {
    setValues((rows) => [...rows, { attribute: "", value: "" }]);
  }

  function updateValue(index: number, patch: Partial<ValueRow>) {
    setValues((rows) =>
      rows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  function removeValue(index: number) {
    setValues((rows) => rows.filter((_, i) => i !== index));
  }

  let error: string | null = null;
  if (mutation.error instanceof ApiError) {
    error =
      mutation.error.status === 409
        ? t("alreadyExists")
        : mutation.error.status === 400
          ? t("invalidInput")
          : mutation.error.status === 403
            ? t("forbidden")
            : mutation.error.detail;
  } else if (mutation.isError) {
    error = tCommon("genericError");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("products.createTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <div className="grid gap-4 md:grid-cols-3">
            <FormField
              id="product_code"
              label={t("code")}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
            <FormField
              id="product_name"
              label={t("name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="product_type">{t("products.productType")}</Label>
              <select
                id="product_type"
                name="product_type"
                value={productType}
                onChange={(e) => setProductType(e.target.value)}
                required
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="" />
                {(typesQuery.data ?? []).map((pt) => (
                  <option key={pt.code} value={pt.code}>
                    {pt.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div>
              <p className="text-sm font-medium">{t("products.values")}</p>
              <p className="text-xs text-muted-foreground">
                {t("products.valuesHint")}
              </p>
            </div>
            {values.map((row, index) => (
              <div
                key={index}
                className="grid items-end gap-4 md:grid-cols-[1fr_1fr_auto]"
              >
                <FormField
                  id={`product_value_attribute_${index}`}
                  label={t("collectionDetail.attribute")}
                  value={row.attribute}
                  onChange={(e) => updateValue(index, { attribute: e.target.value })}
                />
                <FormField
                  id={`product_value_value_${index}`}
                  label={t("collectionDetail.value")}
                  value={row.value}
                  onChange={(e) => updateValue(index, { value: e.target.value })}
                />
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => removeValue(index)}
                >
                  {t("remove")}
                </Button>
              </div>
            ))}
            <div>
              <Button type="button" variant="outline" onClick={addValue}>
                {t("add")}
              </Button>
            </div>
          </div>

          {mutation.isSuccess ? (
            <Alert variant="success">{t("created")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <div>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? tCommon("loading") : t("create")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ProductRow({ product }: { product: Product }) {
  const t = useTranslations("catalog");

  return (
    <TableRow>
      <TableCell className="font-medium">{product.code}</TableCell>
      <TableCell>{product.name}</TableCell>
      <TableCell>{product.product_type}</TableCell>
      <TableCell>
        <Badge variant={product.is_published ? "active" : "inactive"}>
          {product.is_published
            ? t("products.published")
            : t("products.draft")}
        </Badge>
      </TableCell>
      <TableCell>
        <Link
          href={`/admin/catalog/products/${product.code}`}
          className="text-sm font-medium text-primary hover:underline"
        >
          {t("products.manage")}
        </Link>
      </TableCell>
    </TableRow>
  );
}

export function ProductsManager() {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [PRODUCTS_KEY],
    queryFn: listProducts,
  });

  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: [PRODUCTS_KEY] });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("products.title")}</h1>

      <CreateProductForm onCreated={refreshList} />

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("products.empty")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("code")}</TableHead>
              <TableHead>{t("name")}</TableHead>
              <TableHead>{t("products.productType")}</TableHead>
              <TableHead>{t("products.status")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((product) => (
              <ProductRow key={product.code} product={product} />
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
