import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { StorefrontProductDetail } from "@/components/storefront/product-detail";
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

describe("StorefrontProductDetail", () => {
  it("renders the product details", async () => {
    server.use(
      http.get("*/catalog/storefront/products/house-blend/", () =>
        HttpResponse.json(houseBlend),
      ),
    );

    renderWithProviders(<StorefrontProductDetail code="house-blend" />);

    expect(await screen.findByText("House Blend")).toBeInTheDocument();
  });

  it("shows a not-found message on a 404", async () => {
    server.use(
      http.get("*/catalog/storefront/products/house-blend/", () =>
        HttpResponse.json({ detail: "not found" }, { status: 404 }),
      ),
    );

    renderWithProviders(<StorefrontProductDetail code="house-blend" />);

    expect(
      await screen.findByText(messages.storefront.notFound),
    ).toBeInTheDocument();
  });
});
