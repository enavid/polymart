"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import { addCartItem, type Cart } from "@/lib/api/cart";
import {
  getStorefrontProductVariants,
  type StorefrontVariant,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { formatMoneyString, formatPercent } from "@/lib/format";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

/** The PDP's purchasable surface: a product's variants with per-channel price + add-to-cart. */
export function StorefrontProductVariants({ code }: { code: string }) {
  const t = useTranslations("storefront");
  const tCommon = useTranslations("common");
  const channel = STOREFRONT_CHANNEL;

  const query = useQuery({
    queryKey: ["storefront-variants", code, channel],
    queryFn: () => getStorefrontProductVariants(code, channel),
  });

  const variants = query.data?.variants ?? [];
  const taxRate = query.data?.tax_rate ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("variants")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {query.isLoading ? <p>{tCommon("loading")}</p> : null}

        {taxRate != null ? (
          <p className="text-xs text-muted-foreground">
            {t("taxIncluded", { rate: formatPercent(taxRate) })}
          </p>
        ) : null}

        {query.isError ? (
          <Alert variant="destructive">
            {query.error instanceof ApiError
              ? query.error.detail
              : tCommon("genericError")}
          </Alert>
        ) : null}

        {query.data && variants.length === 0 ? (
          <p className="text-muted-foreground">{t("noVariants")}</p>
        ) : null}

        {variants.map((variant) => (
          <VariantRow key={variant.sku} variant={variant} channel={channel} />
        ))}
      </CardContent>
    </Card>
  );
}

function VariantRow({
  variant,
  channel,
}: {
  variant: StorefrontVariant;
  channel: string;
}) {
  const t = useTranslations("storefront");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [quantity, setQuantity] = useState("1");

  const purchasable = variant.price !== null;

  const add = useMutation({
    mutationFn: () =>
      addCartItem({ channel, sku: variant.sku, quantity: Number(quantity) }),
    onSuccess: (cart: Cart) => {
      // Keep the cart page's cache in step with the add so the badge/totals are fresh.
      queryClient.setQueryData(["cart", channel], cart);
    },
  });

  return (
    <div className="flex flex-col gap-2 border-t border-border pt-4 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col">
          <span className="font-medium">{variant.name}</span>
          <span className="text-xs text-muted-foreground">{variant.sku}</span>
        </div>
        <span className="text-sm font-semibold">
          {purchasable
            ? formatMoneyString(variant.price!.amount, variant.price!.currency)
            : t("unavailable")}
        </span>
      </div>

      {variant.values.length > 0 ? (
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {variant.values.map((value) => (
            <span key={value.attribute}>
              {value.attribute}: {value.value}
            </span>
          ))}
        </div>
      ) : null}

      {purchasable ? (
        <div className="flex items-center gap-2">
          <Input
            id={`variant_qty_${variant.sku}`}
            name={`variant_qty_${variant.sku}`}
            type="number"
            aria-label={t("quantity")}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="w-20"
          />
          <Button
            type="button"
            size="sm"
            onClick={() => add.mutate()}
            disabled={add.isPending}
          >
            {t("addToCart")}
          </Button>
        </div>
      ) : null}

      {add.isSuccess ? <Alert variant="success">{t("added")}</Alert> : null}
      {add.isError ? (
        <Alert variant="destructive">
          {add.error instanceof ApiError ? add.error.detail : tCommon("genericError")}
        </Alert>
      ) : null}
    </div>
  );
}
