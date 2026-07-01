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
};

describe("StorefrontProductList", () => {
  it("lists products returned by the storefront API", async () => {
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
});
