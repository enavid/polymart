import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { ProductCard } from "@/components/storefront/product-card";
import messages from "@/i18n/messages/fa.json";
import type { StorefrontProduct } from "@/lib/api/catalog";
import { renderWithProviders } from "@/test/utils";

const base: StorefrontProduct = {
  code: "elec-00",
  name: "هدفون بی‌سیم",
  product_type: "elec",
  values: [],
  metadata: {},
  from_price: "1200000.0000",
  currency: "IRR",
  available: true,
};

describe("ProductCard", () => {
  it("makes the whole card a link to the product, named by the product", () => {
    renderWithProviders(<ProductCard product={base} />);

    const link = screen.getByRole("link", { name: /هدفون بی‌سیم/ });
    expect(link).toHaveAttribute("href", "/products/elec-00");
  });

  it("shows the product name and a Toman 'from' price, not the raw SKU/code", () => {
    renderWithProviders(<ProductCard product={base} />);

    expect(screen.getByText("هدفون بی‌سیم")).toBeInTheDocument();
    // 1,200,000 IRR is rendered as 120,000 Toman (÷10), in Persian digits.
    expect(screen.getByText(/۱۲۰٬۰۰۰/)).toBeInTheDocument();
    // The internal product code is never surfaced to the shopper.
    expect(screen.queryByText("elec-00")).not.toBeInTheDocument();
  });

  it("overlays an out-of-stock badge only when the product is unavailable", () => {
    const { unmount } = renderWithProviders(<ProductCard product={base} />);
    expect(screen.queryByText(messages.storefront.outOfStock)).not.toBeInTheDocument();
    unmount();

    renderWithProviders(<ProductCard product={{ ...base, available: false }} />);
    expect(screen.getByText(messages.storefront.outOfStock)).toBeInTheDocument();
  });

  it("omits the price line when the product carries no channel pricing", () => {
    renderWithProviders(
      <ProductCard
        product={{ ...base, from_price: undefined, currency: undefined, available: undefined }}
      />,
    );

    expect(screen.getByText("هدفون بی‌سیم")).toBeInTheDocument();
    expect(screen.queryByText(messages.storefront.noPrice)).not.toBeInTheDocument();
  });

  it("shows a 'prices include VAT' note when the product carries a tax rate", () => {
    renderWithProviders(<ProductCard product={{ ...base, tax_rate: "9" }} />);
    // The note (with the rate through the app's percent formatter) mentions VAT.
    expect(screen.getByText(/مالیات/)).toBeInTheDocument();
  });

  it("omits the VAT note for an exempt product (null tax rate)", () => {
    renderWithProviders(<ProductCard product={{ ...base, tax_rate: null }} />);
    expect(screen.queryByText(/مالیات/)).not.toBeInTheDocument();
  });
});
