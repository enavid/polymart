"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  getCart,
  removeCartItem,
  updateCartItem,
  type Cart,
} from "@/lib/api/cart";
import { ApiError } from "@/lib/api/client";
import { formatMoneyString } from "@/lib/format";
import { STOREFRONT_CHANNEL } from "@/lib/storefront/channel";

const CART_KEY = (channel: string) => ["cart", channel] as const;

/** The shopper's cart for the active channel: line editing + server-computed totals.
 *
 * Open to guests as well as signed-in users -- the backend resolves the cart from the
 * request's owner (a user, or a guest's HttpOnly session cookie), so no login is
 * required to build or view a cart. */
export function CartView() {
  const t = useTranslations("cart");
  const tCommon = useTranslations("common");
  const channel = STOREFRONT_CHANNEL;
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: CART_KEY(channel),
    queryFn: () => getCart(channel),
  });

  function onMutated(cart: Cart) {
    queryClient.setQueryData(CART_KEY(channel), cart);
  }

  const cart = query.data;
  const hasUnavailable = (cart?.items ?? []).some((line) => !line.available);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {cart && cart.items.length === 0 ? (
        <div className="flex flex-col gap-4">
          <p className="text-muted-foreground">{t("empty")}</p>
          <Link href="/products" className="text-sm text-primary hover:underline">
            {t("continueShopping")}
          </Link>
        </div>
      ) : null}

      {cart && cart.items.length > 0 ? (
        <>
          {hasUnavailable ? <Alert variant="destructive">{t("unavailable")}</Alert> : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("product")}</TableHead>
                <TableHead>{t("unitPrice")}</TableHead>
                <TableHead>{t("quantity")}</TableHead>
                <TableHead>{t("lineTotal")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {cart.items.map((line) => (
                <CartLineRow
                  key={line.sku}
                  line={line}
                  channel={channel}
                  currency={cart.currency}
                  onMutated={onMutated}
                />
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between border-t border-border pt-4">
            <span className="font-medium">{t("total")}</span>
            <span className="text-lg font-semibold">
              {formatMoneyString(cart.total, cart.currency)}
            </span>
          </div>

          {hasUnavailable ? (
            <p className="text-sm text-muted-foreground">{t("checkoutUnavailable")}</p>
          ) : null}

          <div className="flex items-center justify-between">
            <Link href="/products" className="text-sm text-primary hover:underline">
              {t("continueShopping")}
            </Link>
            {/* Checkout is a multi-step flow (choose address, then review + place);
                the cart just navigates into it. Disabled while a line is unavailable
                so the shopper resolves it before checkout. */}
            {hasUnavailable ? (
              <Button type="button" disabled>
                {t("checkout")}
              </Button>
            ) : (
              <Link href="/checkout" className={buttonVariants()}>
                {t("checkout")}
              </Link>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

interface CartLineRowProps {
  line: Cart["items"][number];
  channel: string;
  currency: string;
  onMutated: (cart: Cart) => void;
}

function CartLineRow({ line, channel, currency, onMutated }: CartLineRowProps) {
  const t = useTranslations("cart");
  const tCommon = useTranslations("common");
  const [quantity, setQuantity] = useState(String(line.quantity));

  function mapError(error: unknown): string {
    if (error instanceof ApiError) {
      return error.status === 404 ? t("notFound") : error.detail;
    }
    return tCommon("genericError");
  }

  const update = useMutation({
    mutationFn: () => updateCartItem(line.sku, channel, Number(quantity)),
    onSuccess: onMutated,
  });

  const remove = useMutation({
    mutationFn: () => removeCartItem(line.sku, channel),
    onSuccess: onMutated,
  });

  const error = update.isError
    ? mapError(update.error)
    : remove.isError
      ? mapError(remove.error)
      : null;

  return (
    <>
      <TableRow>
        <TableCell className="font-medium">
          <div className="flex flex-col">
            <span>{line.sku}</span>
            {!line.available ? (
              <span className="text-xs text-destructive">{t("lineUnavailable")}</span>
            ) : null}
          </div>
        </TableCell>
        <TableCell>{formatMoneyString(line.unit_price, currency)}</TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Input
              id={`cart_qty_${line.sku}`}
              name={`cart_qty_${line.sku}`}
              type="number"
              aria-label={t("quantity")}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-20"
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => update.mutate()}
              disabled={update.isPending}
            >
              {t("update")}
            </Button>
          </div>
        </TableCell>
        <TableCell>{formatMoneyString(line.line_total, currency)}</TableCell>
        <TableCell>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
          >
            {t("remove")}
          </Button>
        </TableCell>
      </TableRow>
      {error ? (
        <TableRow>
          <TableCell colSpan={5}>
            <Alert variant="destructive">{error}</Alert>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}
