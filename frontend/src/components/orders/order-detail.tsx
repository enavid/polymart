"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { cancelOrder, getMyOrder, type Order } from "@/lib/api/orders";
import { getPaymentForOrder, type Payment } from "@/lib/api/payments";
import { refundPaymentToWallet } from "@/lib/api/wallet";
import { formatJalaliDateTime, formatMoneyString } from "@/lib/format";
import { useCurrentUser } from "@/lib/hooks/use-auth";
import { orderStatusKey } from "@/lib/orders/status";
import { paymentMethodKey, paymentStatusKey } from "@/lib/payments/labels";

// The happy-path lifecycle, in order, for the status stepper. Cancellation is a
// terminal branch shown separately rather than a step.
const TIMELINE: ReadonlyArray<"pending" | "paid" | "fulfilled"> = [
  "pending",
  "paid",
  "fulfilled",
];

const ORDER_KEY = (number: string) => ["order", number] as const;
const ORDERS_LIST_KEY = ["orders"] as const;
const PAYMENT_KEY = (number: string) => ["payment", "order", number] as const;
const WALLET_KEY = ["wallet"] as const;

/** One of the shopper's own orders: captured lines, status timeline, and cancel.
 *
 * Open to guests as well as signed-in users: the order is resolved from the request's
 * owner (a user, or a guest's HttpOnly session cookie), so a guest reaches the order
 * they just placed. An order that isn't the caller's is a 404, so no owner id in the URL
 * can leak another shopper's order (IDOR-safe for both). */
export function OrderDetail({ number }: { number: string }) {
  const t = useTranslations("orders");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const query = useQuery({
    queryKey: ORDER_KEY(number),
    queryFn: () => getMyOrder(number),
    retry: false,
  });

  const cancel = useMutation({
    mutationFn: () => cancelOrder(number),
    onSuccess: (order) => {
      setConfirming(false);
      queryClient.setQueryData(ORDER_KEY(number), order);
      // The history list now shows a different status; let it refetch.
      queryClient.invalidateQueries({ queryKey: ORDERS_LIST_KEY });
    },
  });

  if (query.isLoading) {
    return <p>{tCommon("loading")}</p>;
  }

  // A missing order (or one owned by someone else) is a 404: show "not found",
  // never leak whether the number exists for another shopper.
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Alert variant="destructive">
          {notFound
            ? t("notFound")
            : query.error instanceof ApiError
              ? query.error.detail
              : tCommon("genericError")}
        </Alert>
        <Link href="/orders" className="text-sm text-primary hover:underline">
          {t("backToList")}
        </Link>
      </div>
    );
  }

  const order = query.data as Order;
  const isCancelled = order.status === "cancelled";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">
          {t("number")}: <span className="font-mono">{order.number}</span>
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("placedAt")}: {formatJalaliDateTime(order.placed_at)}
        </p>
      </div>

      <StatusTimeline order={order} />

      {isCancelled ? <Alert variant="destructive">{t("cancelledNote")}</Alert> : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-muted-foreground">{t("shippingAddress")}</h2>
        <div className="flex flex-col gap-1 rounded-xl border border-border p-4 text-sm">
          <span className="font-medium">{order.shipping_address.recipient_name}</span>
          <span dir="ltr" className="text-muted-foreground">
            {order.shipping_address.phone_number}
          </span>
          <span>{`${order.shipping_address.province}، ${order.shipping_address.city}`}</span>
          <span>{order.shipping_address.line1}</span>
          {order.shipping_address.line2 ? <span>{order.shipping_address.line2}</span> : null}
          <span dir="ltr" className="text-muted-foreground">
            {order.shipping_address.postal_code}
          </span>
        </div>
      </section>

      <PaymentSection number={order.number} />

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("product")}</TableHead>
            <TableHead>{t("unitPrice")}</TableHead>
            <TableHead>{t("quantity")}</TableHead>
            <TableHead>{t("lineTotal")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {order.items.map((line) => (
            <TableRow key={line.sku}>
              <TableCell className="font-medium">{line.sku}</TableCell>
              <TableCell>{formatMoneyString(line.unit_price, order.currency)}</TableCell>
              <TableCell>{line.quantity}</TableCell>
              <TableCell>{formatMoneyString(line.line_total, order.currency)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex items-center justify-between border-t border-border pt-4">
        <span className="font-medium">{t("total")}</span>
        <span className="text-lg font-semibold">
          {formatMoneyString(order.total, order.currency)}
        </span>
      </div>

      {cancel.isError ? (
        <Alert variant="destructive">
          {cancel.error instanceof ApiError ? cancel.error.detail : t("cancelError")}
        </Alert>
      ) : null}

      <div className="flex items-center justify-between">
        <Link href="/orders" className="text-sm text-primary hover:underline">
          {t("backToList")}
        </Link>
        {order.status === "pending" ? (
          confirming ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{t("cancelConfirm")}</span>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
              >
                {t("cancel")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setConfirming(false)}
              >
                {tCommon("back")}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConfirming(true)}
            >
              {t("cancel")}
            </Button>
          )
        ) : null}
      </div>
    </div>
  );
}

/**
 * The order's payment: method and status, read owner-scoped from the payment context.
 *
 * A pending order created before its payment (a rare window, or a legacy order) has none,
 * which the backend returns as a 404; that is shown as a muted "no payment" note rather
 * than an error. The amount is not repeated here -- it is the order total shown below --
 * so there is a single source of truth for money on the page.
 */
function PaymentSection({ number }: { number: string }) {
  const t = useTranslations("payment");

  const query = useQuery({
    queryKey: PAYMENT_KEY(number),
    queryFn: () => getPaymentForOrder(number),
    retry: false,
  });

  if (query.isLoading) {
    return null;
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-muted-foreground">{t("sectionTitle")}</h2>
        <p className="text-sm text-muted-foreground">{notFound ? t("none") : t("loadError")}</p>
      </section>
    );
  }

  const payment = query.data as Payment;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium text-muted-foreground">{t("sectionTitle")}</h2>
      <div className="flex flex-col gap-1 rounded-xl border border-border p-4 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{t("method")}</span>
          <span className="font-medium">{t(paymentMethodKey(payment.method))}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{t("status")}</span>
          <span className="font-medium">{t(paymentStatusKey(payment.status))}</span>
        </div>
        {payment.method === "cod" ? (
          <p className="text-muted-foreground">{t("codHint")}</p>
        ) : null}
        <StaffRefundControl payment={payment} number={number} />
      </div>
    </section>
  );
}

/**
 * A staff-only "refund to wallet" control, shown for a captured payment.
 *
 * Refunding returns the captured amount as store credit to the shopper's wallet and moves
 * the payment to `refunded`. Only rendered for staff and only while the payment is captured,
 * so a shopper never sees it and it disappears once the refund lands. Guards against a double
 * submit while the request is in flight.
 */
function StaffRefundControl({ payment, number }: { payment: Payment; number: string }) {
  const t = useTranslations("payment");
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();

  const refund = useMutation({
    mutationFn: () => refundPaymentToWallet(payment.reference),
    onSuccess: () => {
      // Re-read the payment (now refunded) and the shopper's wallet (now credited).
      void queryClient.invalidateQueries({ queryKey: PAYMENT_KEY(number) });
      void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
    },
  });

  if (!user?.is_staff || payment.status !== "captured") {
    return null;
  }

  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-border pt-2">
      <Button
        variant="outline"
        size="sm"
        onClick={() => refund.mutate()}
        disabled={refund.isPending}
      >
        {refund.isPending ? t("refunding") : t("refundToWallet")}
      </Button>
      {refund.isError ? (
        <Alert variant="destructive">
          {refund.error instanceof ApiError ? refund.error.detail : t("refundError")}
        </Alert>
      ) : null}
    </div>
  );
}

/** A linear stepper over the happy-path statuses, marking the reached ones. */
function StatusTimeline({ order }: { order: Order }) {
  const t = useTranslations("orders");
  const reachedIndex = TIMELINE.indexOf(order.status as (typeof TIMELINE)[number]);

  return (
    <div>
      <p className="mb-2 text-sm font-medium">{t("timeline")}</p>
      <ol className="flex flex-wrap gap-2" aria-label={t("timeline")}>
        {TIMELINE.map((step, index) => {
          const reached = reachedIndex >= index && order.status !== "cancelled";
          return (
            <li
              key={step}
              aria-current={order.status === step ? "step" : undefined}
              className={
                reached
                  ? "rounded-full bg-primary px-3 py-1 text-xs text-primary-foreground"
                  : "rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
              }
            >
              {t(orderStatusKey(step))}
            </li>
          );
        })}
        {order.status === "cancelled" ? (
          <li className="rounded-full bg-destructive px-3 py-1 text-xs text-destructive-foreground">
            {t("statusCancelled")}
          </li>
        ) : null}
      </ol>
    </div>
  );
}
