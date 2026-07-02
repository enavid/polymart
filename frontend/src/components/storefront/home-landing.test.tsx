import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { HomeLanding } from "@/components/storefront/home-landing";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function featured(results: { code: string; name: string }[]) {
  server.use(
    http.get("*/catalog/storefront/products/", () =>
      HttpResponse.json({
        count: results.length,
        limit: 3,
        offset: 0,
        results: results.map((r) => ({
          ...r,
          product_type: "coffee",
          values: [],
          metadata: {},
        })),
      }),
    ),
  );
}

describe("HomeLanding", () => {
  it("shows the hero with a shop call-to-action", async () => {
    featured([]);
    renderWithProviders(<HomeLanding />);

    expect(
      screen.getByRole("heading", { name: messages.home.heroTitle }),
    ).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: messages.home.shopCta });
    expect(cta).toHaveAttribute("href", "/products");
  });

  it("renders featured products from the storefront read API", async () => {
    featured([
      { code: "house-blend", name: "House Blend" },
      { code: "dark-roast", name: "Dark Roast" },
    ]);
    renderWithProviders(<HomeLanding />);

    expect(await screen.findByText("House Blend")).toBeInTheDocument();
    expect(screen.getByText("Dark Roast")).toBeInTheDocument();
    const viewLinks = screen.getAllByRole("link", { name: messages.storefront.viewProduct });
    expect(viewLinks.map((a) => a.getAttribute("href"))).toEqual([
      "/products/house-blend",
      "/products/dark-roast",
    ]);
  });

  it("shows the empty state when there are no products", async () => {
    featured([]);
    renderWithProviders(<HomeLanding />);

    expect(await screen.findByText(messages.home.featuredEmpty)).toBeInTheDocument();
  });
});
