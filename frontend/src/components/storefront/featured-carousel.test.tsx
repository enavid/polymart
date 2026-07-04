import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FeaturedCarousel } from "@/components/storefront/featured-carousel";
import type { StorefrontProduct } from "@/lib/api/catalog";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const home = messages.home;

function product(code: string, name: string): StorefrontProduct {
  return { code, name, product_type: "coffee", values: [], metadata: {} };
}

describe("FeaturedCarousel", () => {
  it("renders each product as a link to its detail page", () => {
    renderWithProviders(
      <FeaturedCarousel products={[product("a", "Alpha"), product("b", "Beta")]} />,
    );

    expect(screen.getByRole("link", { name: /Alpha/ })).toHaveAttribute(
      "href",
      "/products/a",
    );
    expect(screen.getByRole("link", { name: /Beta/ })).toHaveAttribute(
      "href",
      "/products/b",
    );
  });

  it("shows navigation controls when there is more than one product", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <FeaturedCarousel products={[product("a", "Alpha"), product("b", "Beta")]} />,
    );

    const next = screen.getByRole("button", { name: home.carouselNext });
    expect(screen.getByRole("button", { name: home.carouselPrevious })).toBeInTheDocument();
    // Clicking must not throw (scroll is a no-op in jsdom).
    await user.click(next);
  });

  it("hides navigation controls for a single product", () => {
    renderWithProviders(<FeaturedCarousel products={[product("a", "Alpha")]} />);

    expect(screen.queryByRole("button", { name: home.carouselNext })).not.toBeInTheDocument();
  });
});
