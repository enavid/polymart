import { StorefrontProductDetail } from "@/components/storefront/product-detail";
import { StorefrontProductVariants } from "@/components/storefront/product-variants";

export default async function StorefrontProductDetailPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  return (
    <div className="flex flex-col gap-6">
      <StorefrontProductDetail code={code} />
      <StorefrontProductVariants code={code} />
    </div>
  );
}
