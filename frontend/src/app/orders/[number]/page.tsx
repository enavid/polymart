import { OrderDetail } from "@/components/orders/order-detail";

export default async function OrderDetailPage({
  params,
}: {
  params: Promise<{ number: string }>;
}) {
  const { number } = await params;
  return <OrderDetail number={number} />;
}
