import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ProductDetail } from "@/components/admin/catalog/product-detail";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const product = {
  id: 1,
  code: "house-blend",
  name: "House Blend",
  product_type: "coffee",
  values: [],
  metadata: {},
  is_published: false,
};

describe("ProductDetail", () => {
  it("shows the product name", async () => {
    server.use(
      http.get("*/catalog/products/house-blend/", () => HttpResponse.json(product)),
      http.get("*/catalog/products/house-blend/categories/", () =>
        HttpResponse.json({ categories: [] }),
      ),
      http.get("*/catalog/products/house-blend/variants/", () => HttpResponse.json([])),
    );

    renderWithProviders(<ProductDetail code="house-blend" />);

    expect((await screen.findAllByText("House Blend")).length).toBeGreaterThan(0);
  });

  it("toggles publication", async () => {
    let published = false;
    server.use(
      http.get("*/catalog/products/house-blend/", () =>
        HttpResponse.json({ ...product, is_published: published }),
      ),
      http.get("*/catalog/products/house-blend/categories/", () =>
        HttpResponse.json({ categories: [] }),
      ),
      http.get("*/catalog/products/house-blend/variants/", () => HttpResponse.json([])),
      http.put("*/catalog/products/house-blend/publication/", () => {
        published = true;
        return HttpResponse.json({ ...product, is_published: true });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductDetail code="house-blend" />);

    await user.click(
      await screen.findByRole("button", {
        name: messages.catalog.productDetail.publish,
      }),
    );

    expect(
      await screen.findByRole("button", {
        name: messages.catalog.productDetail.unpublish,
      }),
    ).toBeInTheDocument();
  });
});
