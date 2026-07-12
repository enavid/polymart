import { ShippingLabelView } from "@/components/admin/orders/shipping-label-view";

export default async function ShippingLabelPage({
  params,
}: {
  params: Promise<{ number: string }>;
}) {
  const { number } = await params;
  return <ShippingLabelView number={number} />;
}
