import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { StorefrontProductList } from "@/components/storefront/product-list";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const houseBlend = {
  code: "house-blend",
  name: "House Blend",
  product_type: "coffee",
  values: [],
  metadata: {},
  from_price: "120000.0000",
  currency: "IRR",
  available: true,
};

const outOfStock = {
  code: "light-roast",
  name: "Light Roast",
  product_type: "coffee",
  values: [],
  metadata: {},
  from_price: "100000.0000",
  currency: "IRR",
  available: false,
};

/** Register the public taxonomy endpoints that populate the filter dropdowns. */
function taxonomy() {
  server.use(
    http.get("*/catalog/storefront/categories/", () =>
      HttpResponse.json([{ slug: "coffee-beans", name: "Coffee Beans", parent: "hot-drinks" }]),
    ),
    http.get("*/catalog/storefront/collections/", () =>
      HttpResponse.json([{ slug: "featured", name: "Featured" }]),
    ),
    http.get("*/catalog/storefront/product-types/", () =>
      HttpResponse.json([{ code: "coffee", name: "Coffee" }]),
    ),
  );
}

describe("StorefrontProductList", () => {
  it("lists products returned by the storefront API", async () => {
    taxonomy();
    server.use(
      http.get("*/catalog/storefront/products/*", () =>
        HttpResponse.json({
          count: 1,
          limit: 12,
          offset: 0,
          results: [houseBlend],
        }),
      ),
    );

    renderWithProviders(<StorefrontProductList />);

    expect(await screen.findByText("House Blend")).toBeInTheDocument();
  });

  it("shows an empty state when there are no products", async () => {
    taxonomy();
    server.use(
      http.get("*/catalog/storefront/products/*", () =>
        HttpResponse.json({ count: 0, limit: 12, offset: 0, results: [] }),
      ),
    );

    renderWithProviders(<StorefrontProductList />);

    expect(
      await screen.findByText(messages.storefront.empty),
    ).toBeInTheDocument();
  });

  it("shows a 'from' price and an out-of-stock badge per card", async () => {
    taxonomy();
    server.use(
      http.get("*/catalog/storefront/products/*", () =>
        HttpResponse.json({
          count: 2,
          limit: 12,
          offset: 0,
          results: [houseBlend, outOfStock],
        }),
      ),
    );

    renderWithProviders(<StorefrontProductList />);

    // The card shows the localized "from" price (server value, Intl-formatted):
    // match the stable Persian-grouped digits (bidi/space marks vary).
    expect(await screen.findByText(/۱۲۰٬۰۰۰/)).toBeInTheDocument();
    // The out-of-stock product is flagged; the in-stock one is not.
    expect(screen.getByText(messages.storefront.outOfStock)).toBeInTheDocument();
  });

  it("populates the filter dropdowns from the taxonomy endpoints", async () => {
    taxonomy();
    server.use(
      http.get("*/catalog/storefront/products/*", () =>
        HttpResponse.json({ count: 0, limit: 12, offset: 0, results: [] }),
      ),
    );

    renderWithProviders(<StorefrontProductList />);

    // The category dropdown offers the seeded category as an option (not a raw
    // text field where the shopper must type a slug).
    const categorySelect = await screen.findByLabelText(messages.storefront.filterCategory);
    expect(categorySelect.tagName).toBe("SELECT");
    expect(
      await screen.findByRole("option", { name: "Coffee Beans" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Featured" })).toBeInTheDocument();
  });
});
