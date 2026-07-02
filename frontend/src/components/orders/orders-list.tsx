"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { listMyOrders } from "@/lib/api/orders";
import { formatJalaliDateTime, formatMoneyString } from "@/lib/format";
import { useCurrentUser } from "@/lib/hooks/use-auth";
import { orderStatusKey } from "@/lib/orders/status";

const ORDERS_KEY = ["orders"] as const;

/** The authenticated shopper's own order history (newest first). */
export function OrdersList() {
  const t = useTranslations("orders");
  const tCommon = useTranslations("common");

  const { data: user, isLoading: userLoading } = useCurrentUser();

  const query = useQuery({
    queryKey: ORDERS_KEY,
    queryFn: () => listMyOrders(),
    // Orders live behind auth; only fetch once we know there is a user.
    enabled: Boolean(user),
  });

  if (userLoading) {
    return <p>{tCommon("loading")}</p>;
  }

  if (!user) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Alert>{t("loginRequired")}</Alert>
        <Link href="/login" className="text-sm text-primary hover:underline">
          {t("goLogin")}
        </Link>
      </div>
    );
  }

  const page = query.data;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError ? query.error.detail : t("loadError")}
        </Alert>
      ) : null}

      {page && page.results.length === 0 ? (
        <div className="flex flex-col gap-4">
          <p className="text-muted-foreground">{t("empty")}</p>
          <Link href="/products" className="text-sm text-primary hover:underline">
            {t("continueShopping")}
          </Link>
        </div>
      ) : null}

      {page && page.results.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("number")}</TableHead>
              <TableHead>{t("placedAt")}</TableHead>
              <TableHead>{t("status")}</TableHead>
              <TableHead>{t("total")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.results.map((order) => (
              <TableRow key={order.number}>
                <TableCell className="font-medium">{order.number}</TableCell>
                <TableCell>{formatJalaliDateTime(order.placed_at)}</TableCell>
                <TableCell>{t(orderStatusKey(order.status))}</TableCell>
                <TableCell>{formatMoneyString(order.total, order.currency)}</TableCell>
                <TableCell>
                  <Link
                    href={`/orders/${order.number}`}
                    className="text-sm text-primary hover:underline"
                  >
                    {t("view")}
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
