"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

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
import {
  confirmCardToCardPayment,
  getCardToCardInstructions,
  getPaymentForOrder,
  rejectCardToCardPayment,
  submitTransferReference,
  type Payment,
} from "@/lib/api/payments";
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
const CARD_TO_CARD_KEY = (number: string) => ["card-to-card", number] as const;
const WALLET_KEY = ["wallet"] as const;

// An online payment captures out of band (a gateway callback settles it on the server). When
// the shopper is redirected back before that settles, the payment is still `pending`; the page
// polls until it resolves rather than showing a stale "unpaid" state. Bounded, so a genuinely
// abandoned payment stops polling and offers a manual re-check instead of spinning forever.
const ONLINE_POLL_INTERVAL_MS = 2000;
const ONLINE_POLL_MAX_ATTEMPTS = 10;

/** Whether a payment is an online one still awaiting its gateway callback to settle. */
function isSettlingOnline(payment: Payment | undefined): boolean {
  return payment?.method === "online" && payment?.status === "pending";
}

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

      <dl className="flex flex-col gap-2 border-t border-border pt-4 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground">{t("subtotal")}</dt>
          <dd>{formatMoneyString(order.subtotal, order.currency)}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground">
            {t("shipping")}
            {order.shipping_method_name ? (
              <span className="text-muted-foreground"> · {order.shipping_method_name}</span>
            ) : null}
          </dt>
          <dd>{formatMoneyString(order.shipping_cost, order.currency)}</dd>
        </div>
        <div className="flex items-center justify-between border-t border-border pt-2">
          <dt className="font-medium">{t("total")}</dt>
          <dd className="text-lg font-semibold">
            {formatMoneyString(order.total, order.currency)}
          </dd>
        </div>
      </dl>

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
  // Count the polls taken while an online payment is settling, so polling is bounded.
  const [pollAttempts, setPollAttempts] = useState(0);

  const query = useQuery({
    queryKey: PAYMENT_KEY(number),
    queryFn: () => getPaymentForOrder(number),
    retry: false,
    refetchInterval: (q) =>
      isSettlingOnline(q.state.data) && pollAttempts < ONLINE_POLL_MAX_ATTEMPTS
        ? ONLINE_POLL_INTERVAL_MS
        : false,
  });

  const settling = isSettlingOnline(query.data);
  const pollExhausted = pollAttempts >= ONLINE_POLL_MAX_ATTEMPTS;

  // Tick the attempt counter once per completed read while the payment is still settling.
  useEffect(() => {
    if (settling) {
      setPollAttempts((n) => n + 1);
    }
  }, [query.dataUpdatedAt, settling]);

  const recheck = () => {
    setPollAttempts(0);
    void query.refetch();
  };

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
        {settling ? (
          <OnlineAwaitingBanner exhausted={pollExhausted} onRecheck={recheck} />
        ) : null}
        {payment.method === "cod" ? (
          <p className="text-muted-foreground">{t("codHint")}</p>
        ) : null}
        {payment.method === "card_to_card" ? (
          <CardToCardBuyerBlock payment={payment} number={number} />
        ) : null}
        {payment.method === "card_to_card" ? (
          <StaffCardToCardControl payment={payment} number={number} />
        ) : null}
        <StaffRefundControl payment={payment} number={number} />
      </div>
    </section>
  );
}

/**
 * The "awaiting the gateway callback" banner for an online payment that is still settling.
 *
 * While polling, it shows a live "confirming your payment" note (the page auto-refreshes until
 * the payment resolves to paid/failed). Once the bounded polling is exhausted -- a genuinely
 * stuck or abandoned payment -- it stops and offers a manual re-check instead of spinning
 * forever. The status text itself is the server's, never inferred here.
 */
function OnlineAwaitingBanner({
  exhausted,
  onRecheck,
}: {
  exhausted: boolean;
  onRecheck: () => void;
}) {
  const t = useTranslations("payment");

  if (exhausted) {
    return (
      <div
        data-testid="online-awaiting"
        className="mt-2 flex flex-col gap-2 border-t border-border pt-2"
      >
        <p className="text-muted-foreground">{t("awaitingExhausted")}</p>
        <Button variant="outline" size="sm" onClick={onRecheck}>
          {t("checkAgain")}
        </Button>
      </div>
    );
  }

  return (
    <div
      data-testid="online-awaiting"
      role="status"
      aria-live="polite"
      className="mt-2 flex items-center gap-2 border-t border-border pt-2 text-muted-foreground"
    >
      <span
        aria-hidden
        className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent"
      />
      <span>{t("awaitingConfirmation")}</span>
    </div>
  );
}

/**
 * The buyer's card-to-card panel, shown while the payment is pending: the merchant's
 * destination card (fetched owner-scoped from the server -- never entered by the buyer) plus
 * a one-time form to report the transfer reference. Once submitted, it shows the reported
 * reference and an "awaiting staff confirmation" note. Nothing is shown once the payment is
 * settled (captured/failed), so the block disappears when staff confirm or reject.
 */
function CardToCardBuyerBlock({ payment, number }: { payment: Payment; number: string }) {
  const t = useTranslations("payment");
  const queryClient = useQueryClient();
  const [reference, setReference] = useState("");

  const isPending = payment.status === "pending";
  const instructions = useQuery({
    queryKey: CARD_TO_CARD_KEY(number),
    queryFn: () => getCardToCardInstructions(number),
    enabled: isPending,
    retry: false,
  });

  const submit = useMutation({
    mutationFn: () => submitTransferReference(number, reference.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PAYMENT_KEY(number) });
    },
  });

  // Only meaningful while the transfer is still awaiting confirmation.
  if (!isPending) {
    return null;
  }

  const alreadySubmitted = payment.transfer_reference !== null;

  return (
    <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3">
      <p className="text-muted-foreground">{t("cardToCardInstructions")}</p>
      {instructions.data ? (
        <dl className="flex flex-col gap-1 rounded-lg bg-muted/40 p-3">
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">{t("cardNumber")}</dt>
            <dd dir="ltr" className="font-mono font-medium tabular-nums">
              {instructions.data.card_number}
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-muted-foreground">{t("cardHolder")}</dt>
            <dd className="font-medium">{instructions.data.card_holder}</dd>
          </div>
        </dl>
      ) : null}

      {alreadySubmitted ? (
        <div className="flex flex-col gap-1">
          <p className="font-medium text-foreground">{t("transferAwaitingConfirmation")}</p>
          <p className="text-muted-foreground">
            {t("transferReferenceLabel")}: <span dir="ltr">{payment.transfer_reference}</span>
          </p>
        </div>
      ) : (
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (reference.trim() && !submit.isPending) {
              submit.mutate();
            }
          }}
        >
          <label htmlFor="transfer_reference" className="text-muted-foreground">
            {t("transferReferencePrompt")}
          </label>
          <input
            id="transfer_reference"
            name="transfer_reference"
            type="text"
            inputMode="numeric"
            dir="ltr"
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            maxLength={64}
            required
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
          />
          <Button type="submit" size="sm" disabled={!reference.trim() || submit.isPending}>
            {submit.isPending ? t("submittingTransfer") : t("submitTransfer")}
          </Button>
          {submit.isError ? (
            <Alert variant="destructive">
              {submit.error instanceof ApiError ? submit.error.detail : t("submitTransferError")}
            </Alert>
          ) : null}
        </form>
      )}
    </div>
  );
}

/**
 * A staff-only confirm/reject control for a pending card-to-card payment.
 *
 * Confirming captures the payment (the order becomes paid); rejecting fails it (the order is
 * freed for a fresh attempt). Only rendered for staff and only while the payment is pending;
 * confirm is disabled until the buyer has reported a transfer reference to verify. Mirrors the
 * staff refund control, guarding against a double submit while a request is in flight.
 */
function StaffCardToCardControl({ payment, number }: { payment: Payment; number: string }) {
  const t = useTranslations("payment");
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: PAYMENT_KEY(number) });
    void queryClient.invalidateQueries({ queryKey: ORDER_KEY(number) });
  };

  const confirm = useMutation({
    mutationFn: () => confirmCardToCardPayment(payment.reference),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: () => rejectCardToCardPayment(payment.reference),
    onSuccess: invalidate,
  });

  if (!user?.is_staff || payment.status !== "pending") {
    return null;
  }

  const busy = confirm.isPending || reject.isPending;
  const error = confirm.error ?? reject.error;

  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-border pt-2">
      <p className="text-xs text-muted-foreground">{t("staffCardToCardHint")}</p>
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => confirm.mutate()}
          disabled={busy || payment.transfer_reference === null}
        >
          {confirm.isPending ? t("confirming") : t("confirmTransfer")}
        </Button>
        <Button variant="outline" size="sm" onClick={() => reject.mutate()} disabled={busy}>
          {reject.isPending ? t("rejecting") : t("rejectTransfer")}
        </Button>
      </div>
      {confirm.isError || reject.isError ? (
        <Alert variant="destructive">
          {error instanceof ApiError ? error.detail : t("staffCardToCardError")}
        </Alert>
      ) : null}
    </div>
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
