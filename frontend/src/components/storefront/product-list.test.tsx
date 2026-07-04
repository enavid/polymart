import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { StorefrontProductList } from "@/components/storefront/product-list";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

// The search term is read from the URL (`?q=…`); default to no term.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

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

    // The card shows the localized "from" price (server value in Toman, the IRR
    // amount ÷10): match the stable Persian-grouped digits (bidi/space marks vary).
    expect(await screen.findByText(/۱۲٬۰۰۰/)).toBeInTheDocument();
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

  it("sends the price range to the API as Rial (Toman ×10)", async () => {
    taxonomy();
    const urls: string[] = [];
    server.use(
      http.get("*/catalog/storefront/products/*", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ count: 0, limit: 12, offset: 0, results: [] });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<StorefrontProductList />);
    await screen.findByText(messages.storefront.empty);

    await user.type(screen.getByLabelText(messages.storefront.priceMin), "100");
    await user.type(screen.getByLabelText(messages.storefront.priceMax), "500");
    await user.click(
      screen.getByRole("button", { name: messages.storefront.applyFilters }),
    );

    await waitFor(() => {
      const last = urls[urls.length - 1];
      // 100 Toman -> 1000 Rial, 500 Toman -> 5000 Rial.
      expect(last).toContain("min_price=1000");
      expect(last).toContain("max_price=5000");
    });
  });

  it("shows numbered pagination and navigates to another page", async () => {
    taxonomy();
    const urls: string[] = [];
    server.use(
      http.get("*/catalog/storefront/products/*", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ count: 30, limit: 12, offset: 0, results: [houseBlend] });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<StorefrontProductList />);
    await screen.findByText("House Blend");

    // 30 items / 12 per page = 3 pages; page 2 is button "۲" (Persian digit).
    await user.click(screen.getByRole("button", { name: "۲" }));

    await waitFor(() => expect(urls[urls.length - 1]).toContain("offset=12"));
  });
});
