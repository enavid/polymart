import { ProductDetail } from "@/components/admin/catalog/product-detail";

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  return <ProductDetail code={code} />;
}
