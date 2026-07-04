import { VariantDetail } from "@/components/admin/catalog/variant-detail";

export default async function VariantDetailPage({
  params,
}: {
  params: Promise<{ sku: string }>;
}) {
  const { sku } = await params;
  return <VariantDetail sku={sku} />;
}
