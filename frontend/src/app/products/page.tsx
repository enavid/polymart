import { Suspense } from "react";

import { StorefrontProductList } from "@/components/storefront/product-list";

// The product list reads the search/filter query string via `useSearchParams()` in a
// client component. Next needs that behind a Suspense boundary, otherwise the static
// prerender of this route bails out and the production build fails. The list renders its
// own loading UI once mounted, so a null fallback is fine here.
export default function StorefrontProductsPage() {
  return (
    <Suspense fallback={null}>
      <StorefrontProductList />
    </Suspense>
  );
}
