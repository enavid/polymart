"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
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
  adjustVariantStock,
  getVariant,
  getVariantPrices,
  getVariantStock,
  setVariantPrices,
  setVariantStock,
  type Variant,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

interface PriceRow {
  channel: string;
  amount: string;
}

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

function InfoCard({ variant }: { variant: Variant }) {
  const t = useTranslations("catalog");

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("variantDetail.info")}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-2 text-sm">
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("productDetail.title")}</dt>
            <dd>{variant.product}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("productDetail.sku")}</dt>
            <dd className="font-medium">{variant.sku}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="text-muted-foreground">{t("name")}</dt>
            <dd>{variant.name}</dd>
          </div>
        </dl>

        <h3 className="mt-4 text-sm font-medium">{t("products.values")}</h3>
        {variant.values.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("none")}</p>
        ) : (
          <ul className="text-sm">
            {variant.values.map((value) => (
              <li key={value.attribute}>
                {value.attribute} = {value.value}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function PricesCard({ sku }: { sku: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<PriceRow[]>([]);

  const query = useQuery({
    queryKey: ["variant-prices", sku],
    queryFn: () => getVariantPrices(sku),
  });

  useEffect(() => {
    if (query.data) {
      setRows(query.data.map((price) => ({ channel: price.channel, amount: price.amount })));
    }
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: () => setVariantPrices(sku, rows),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["variant-prices", sku] });
    },
  });

  function updateRow(index: number, patch: Partial<PriceRow>) {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  function addRow() {
    setRows((current) => [...current, { channel: "", amount: "" }]);
  }

  function removeRow(index: number) {
    setRows((current) => current.filter((_, i) => i !== index));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("variantDetail.prices")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {query.isLoading ? <p>{tCommon("loading")}</p> : null}

          {query.data && query.data.length === 0 ? (
            <p className="text-muted-foreground">{t("variantDetail.noPrices")}</p>
          ) : null}

          {query.data && query.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("variantDetail.channel")}</TableHead>
                  <TableHead>{t("variantDetail.amount")}</TableHead>
                  <TableHead>{t("variantDetail.currency")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.map((price) => (
                  <TableRow key={price.channel}>
                    <TableCell className="font-medium">{price.channel}</TableCell>
                    <TableCell>{price.amount}</TableCell>
                    <TableCell>{price.currency}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}

          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
            {rows.map((row, index) => (
              <div key={index} className="grid gap-4 md:grid-cols-3 md:items-end">
                <FormField
                  id={`price_channel_${index}`}
                  label={t("variantDetail.channel")}
                  value={row.channel}
                  onChange={(e) => updateRow(index, { channel: e.target.value })}
                />
                <FormField
                  id={`price_amount_${index}`}
                  label={t("variantDetail.amount")}
                  value={row.amount}
                  onChange={(e) => updateRow(index, { amount: e.target.value })}
                />
                <div>
                  <Button type="button" variant="ghost" onClick={() => removeRow(index)}>
                    {t("remove")}
                  </Button>
                </div>
              </div>
            ))}
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={addRow}>
                {t("variantDetail.addPrice")}
              </Button>
            </div>
            {mutation.isSuccess ? (
              <Alert variant="success">{t("saved")}</Alert>
            ) : null}
            {error ? <Alert variant="destructive">{error}</Alert> : null}
            <div>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? tCommon("loading") : t("variantDetail.savePrices")}
              </Button>
            </div>
          </form>
        </div>
      </CardContent>
    </Card>
  );
}

function StockCard({ sku }: { sku: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [quantity, setQuantity] = useState("");
  const [delta, setDelta] = useState("");

  const query = useQuery({
    queryKey: ["variant-stock", sku],
    queryFn: () => getVariantStock(sku),
  });

  const setMutation = useMutation({
    mutationFn: () => setVariantStock(sku, Number(quantity)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["variant-stock", sku] });
    },
  });

  const adjustMutation = useMutation({
    mutationFn: () => adjustVariantStock(sku, Number(delta)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["variant-stock", sku] });
    },
  });

  function onSetSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMutation.mutate();
  }

  function onAdjustSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    adjustMutation.mutate();
  }

  const setError = errorMessage(setMutation.error, setMutation.isError, t, tCommon);

  let adjustError: string | null = null;
  if (adjustMutation.error instanceof ApiError) {
    adjustError =
      adjustMutation.error.status === 400
        ? t("variantDetail.oversell")
        : adjustMutation.error.status === 403
          ? t("forbidden")
          : adjustMutation.error.detail;
  } else if (adjustMutation.isError) {
    adjustError = tCommon("genericError");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("variantDetail.stock")}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-4">
          {query.isLoading ? <p>{tCommon("loading")}</p> : null}

          {query.data !== undefined ? (
            <p className="text-sm">
              {t("variantDetail.quantity")}: <span className="font-medium">{query.data}</span>
            </p>
          ) : null}

          <form onSubmit={onSetSubmit} className="grid gap-4 md:grid-cols-2 md:items-end" noValidate>
            <FormField
              id="stock_quantity"
              label={t("variantDetail.quantity")}
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
            {setError ? (
              <Alert variant="destructive" className="md:col-span-2">
                {setError}
              </Alert>
            ) : null}
            <div>
              <Button type="submit" disabled={setMutation.isPending}>
                {setMutation.isPending ? tCommon("loading") : t("variantDetail.setStock")}
              </Button>
            </div>
          </form>

          <form onSubmit={onAdjustSubmit} className="grid gap-4 md:grid-cols-2 md:items-end" noValidate>
            <FormField
              id="stock_delta"
              label={t("variantDetail.delta")}
              type="number"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
            />
            {adjustError ? (
              <Alert variant="destructive" className="md:col-span-2">
                {adjustError}
              </Alert>
            ) : null}
            <div>
              <Button type="submit" disabled={adjustMutation.isPending}>
                {adjustMutation.isPending ? tCommon("loading") : t("variantDetail.apply")}
              </Button>
            </div>
          </form>
        </div>
      </CardContent>
    </Card>
  );
}

export function VariantDetail({ sku }: { sku: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: ["variant", sku],
    queryFn: () => getVariant(sku),
  });

  return (
    <div className="flex flex-col gap-6">
      <Link href="/admin/catalog/products" className="text-sm text-muted-foreground">
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
          <InfoCard variant={query.data} />
          <PricesCard sku={sku} />
          <StockCard sku={sku} />
        </>
      ) : null}
    </div>
  );
}
