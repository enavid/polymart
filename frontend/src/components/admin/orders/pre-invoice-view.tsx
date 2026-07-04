"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getPreInvoice } from "@/lib/api/orders";
import { formatJalaliDateTime, formatMoneyString } from "@/lib/format";

interface PreInvoiceViewProps {
  number: string;
}

/**
 * A printable pre-invoice (proforma) for one order. Read-only: every money value is the
 * exact server string rendered as-is (never recomputed). The Print button uses the
 * browser's own print dialog; a `no-print` class hides the controls on paper.
 */
export function PreInvoiceView({ number }: PreInvoiceViewProps) {
  const t = useTranslations("preInvoice");
  const tOrders = useTranslations("orders");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: ["pre-invoice", number],
    queryFn: () => getPreInvoice(number),
  });

  if (query.isPending) {
    return <Loading label={tCommon("loading")} />;
  }
  if (query.isError) {
    return <Alert variant="destructive">{t("loadError")}</Alert>;
  }

  const invoice = query.data;
  const address = invoice.shipping_address;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <Button type="button" className="no-print" onClick={() => window.print()}>
          {t("print")}
        </Button>
      </div>

      <div className="flex flex-col gap-1 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">{tOrders("number")}</span>
          <span dir="ltr" className="font-medium">
            {invoice.number}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{tOrders("placedAt")}</span>
          <span>{formatJalaliDateTime(invoice.placed_at)}</span>
        </div>
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-muted-foreground">{t("issuedFor")}</h2>
        <div className="flex flex-col gap-1 rounded-xl border border-border p-4 text-sm">
          <span className="font-medium">{address.recipient_name}</span>
          <span dir="ltr" className="text-muted-foreground">
            {address.phone_number}
          </span>
          <span>{`${address.province}، ${address.city}`}</span>
          <span>{address.line1}</span>
          {address.line2 ? <span>{address.line2}</span> : null}
          <span dir="ltr" className="text-muted-foreground">
            {address.postal_code}
          </span>
        </div>
      </section>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{tOrders("product")}</TableHead>
            <TableHead>{tOrders("unitPrice")}</TableHead>
            <TableHead>{tOrders("quantity")}</TableHead>
            <TableHead>{tOrders("lineTotal")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoice.items.map((line) => (
            <TableRow key={line.sku}>
              <TableCell className="font-medium">{line.sku}</TableCell>
              <TableCell>{formatMoneyString(line.unit_price, invoice.currency)}</TableCell>
              <TableCell>{line.quantity}</TableCell>
              <TableCell>{formatMoneyString(line.line_total, invoice.currency)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex flex-col gap-2 border-t border-border pt-4 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{tOrders("total")}</span>
          <span>{formatMoneyString(invoice.total, invoice.currency)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{t("tax")}</span>
          {/* Tax is computed in a later phase; the server sends null, shown as a note. */}
          <span className="text-muted-foreground">{invoice.tax ?? t("taxPending")}</span>
        </div>
        <div className="flex items-center justify-between border-t border-border pt-2">
          <span className="font-medium">{t("grandTotal")}</span>
          <span className="text-lg font-semibold">
            {formatMoneyString(invoice.grand_total, invoice.currency)}
          </span>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{t("proformaNote")}</p>
    </div>
  );
}
