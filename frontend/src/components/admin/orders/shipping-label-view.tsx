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
import { formatJalaliDateTime } from "@/lib/format";

interface ShippingLabelViewProps {
  number: string;
}

/**
 * A printable shipping label / packing slip for one order. Staff-only (reads through the
 * `manage_orders` pre-invoice endpoint, which carries the captured address and any shipment).
 * Read-only: the destination address, the line items to pack, and the captured carrier +
 * tracking once shipped. The Print button uses the browser's own dialog; `no-print` hides the
 * controls on paper. A pickup order has no address, so the label shows a pickup note instead.
 */
export function ShippingLabelView({ number }: ShippingLabelViewProps) {
  const t = useTranslations("shippingLabel");
  const tOrders = useTranslations("orders");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: ["shipping-label", number],
    queryFn: () => getPreInvoice(number),
  });

  if (query.isPending) {
    return <Loading label={tCommon("loading")} />;
  }
  if (query.isError) {
    return <Alert variant="destructive">{t("loadError")}</Alert>;
  }

  const order = query.data;
  const address = order.shipping_address;

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
            {order.number}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{tOrders("placedAt")}</span>
          <span>{formatJalaliDateTime(order.placed_at)}</span>
        </div>
      </div>

      {address ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">{t("shipTo")}</h2>
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
      ) : (
        <Alert>{t("pickupNote")}</Alert>
      )}

      {order.fulfillment ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">{t("shipment")}</h2>
          <div className="flex flex-col gap-1 rounded-xl border border-border p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">{tOrders("carrier")}</span>
              <span className="font-medium">{order.fulfillment.carrier}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">{tOrders("trackingNumber")}</span>
              <span dir="ltr" className="font-mono">
                {order.fulfillment.tracking_number}
              </span>
            </div>
          </div>
        </section>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-muted-foreground">{t("packingList")}</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{tOrders("product")}</TableHead>
              <TableHead>{tOrders("quantity")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {order.items.map((line) => (
              <TableRow key={line.sku}>
                <TableCell className="font-medium">{line.sku}</TableCell>
                <TableCell>{line.quantity}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <p className="text-xs text-muted-foreground">{t("note")}</p>
    </div>
  );
}
