import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { ProductRow } from "@/components/storefront/product-row";
import type { StorefrontProduct } from "@/lib/api/catalog";
import { renderWithProviders } from "@/test/utils";

function product(code: string, name: string): StorefrontProduct {
  return { code, name, product_type: "coffee", values: [], metadata: {} };
}

describe("ProductRow", () => {
  it("renders the title, a view-all link, and the product cards", () => {
    renderWithProviders(
      <ProductRow
        title="Coffee Beans"
        viewAllHref="/products?category=coffee-beans"
        viewAllLabel="مشاهدهٔ همه"
        products={[product("a", "Alpha"), product("b", "Beta")]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Coffee Beans" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "مشاهدهٔ همه" })).toHaveAttribute(
      "href",
      "/products?category=coffee-beans",
    );
    expect(screen.getByRole("link", { name: /Alpha/ })).toHaveAttribute("href", "/products/a");
    expect(screen.getByRole("link", { name: /Beta/ })).toHaveAttribute("href", "/products/b");
  });

  it("shows an optional subtitle when given", () => {
    renderWithProviders(
      <ProductRow
        title="Coffee Beans"
        subtitle="Freshly roasted"
        viewAllHref="/products"
        viewAllLabel="مشاهدهٔ همه"
        products={[product("a", "Alpha")]}
      />,
    );

    expect(screen.getByText("Freshly roasted")).toBeInTheDocument();
  });
});
