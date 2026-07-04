"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
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
import { createProductType, listProductTypes } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

const PRODUCT_TYPES_KEY = "catalog-product-types";

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function CreateProductTypeForm({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [attributes, setAttributes] = useState("");
  const [variantAttributes, setVariantAttributes] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createProductType({
        code,
        name,
        attributes: splitCsv(attributes),
        variant_attributes: splitCsv(variantAttributes),
      }),
    onSuccess: () => {
      setCode("");
      setName("");
      setAttributes("");
      setVariantAttributes("");
      onCreated();
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
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
        <CardTitle>{t("productTypes.createTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-2" noValidate>
          <FormField
            id="product_type_code"
            label={t("code")}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <FormField
            id="product_type_name"
            label={t("name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <FormField
            id="product_type_attributes"
            label={t("productTypes.attributes")}
            value={attributes}
            onChange={(e) => setAttributes(e.target.value)}
            hint={t("productTypes.attributesHint")}
          />
          <FormField
            id="product_type_variant_attributes"
            label={t("productTypes.variantAttributes")}
            value={variantAttributes}
            onChange={(e) => setVariantAttributes(e.target.value)}
            hint={t("productTypes.attributesHint")}
          />
          {mutation.isSuccess ? (
            <Alert variant="success" className="md:col-span-2">
              {t("created")}
            </Alert>
          ) : null}
          {error ? (
            <Alert variant="destructive" className="md:col-span-2">
              {error}
            </Alert>
          ) : null}
          <div className="md:col-span-2">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? tCommon("loading") : t("create")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function ProductTypesManager() {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [PRODUCT_TYPES_KEY],
    queryFn: listProductTypes,
  });

  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: [PRODUCT_TYPES_KEY] });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("productTypes.title")}</h1>

      <CreateProductTypeForm onCreated={refreshList} />

      {query.isLoading ? <Loading label={tCommon("loading")} /> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("productTypes.empty")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("code")}</TableHead>
              <TableHead>{t("name")}</TableHead>
              <TableHead>{t("productTypes.attributes")}</TableHead>
              <TableHead>{t("productTypes.variantAttributes")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((productType) => (
              <TableRow key={productType.code}>
                <TableCell className="font-medium">{productType.code}</TableCell>
                <TableCell>{productType.name}</TableCell>
                <TableCell>{productType.attributes.join("، ")}</TableCell>
                <TableCell>{productType.variant_attributes.join("، ")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
