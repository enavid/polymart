import { PreInvoiceView } from "@/components/admin/orders/pre-invoice-view";

export default async function PreInvoicePage({
  params,
}: {
  params: Promise<{ number: string }>;
}) {
  const { number } = await params;
  return <PreInvoiceView number={number} />;
}
