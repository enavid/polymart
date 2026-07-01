import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ProductsManager } from "@/components/admin/catalog/products-manager";
import messages from "@/i18n/messages/fa.json";
import { renderWithProviders } from "@/test/utils";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const espresso = {
  id: 1,
  code: "espresso",
  name: "Espresso",
  product_type: "coffee",
  values: [],
  metadata: {},
  is_published: false,
};

describe("ProductsManager", () => {
  it("lists products with their status", async () => {
    server.use(
      http.get("*/catalog/products/", () => HttpResponse.json([espresso])),
      http.get("*/catalog/product-types/", () => HttpResponse.json([])),
    );

    renderWithProviders(<ProductsManager />);

    expect(await screen.findByText("espresso")).toBeInTheDocument();
    expect(screen.getByText(messages.catalog.products.draft)).toBeInTheDocument();
  });

  it("creates a product and refreshes the list", async () => {
    let created = false;
    server.use(
      http.get("*/catalog/product-types/", () =>
        HttpResponse.json([
          {
            id: 1,
            code: "coffee",
            name: "Coffee",
            attributes: [],
            variant_attributes: [],
          },
        ]),
      ),
      http.get("*/catalog/products/", () =>
        HttpResponse.json(created ? [espresso] : []),
      ),
      http.post("*/catalog/products/", async () => {
        created = true;
        return HttpResponse.json(espresso, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<ProductsManager />);

    await screen.findByText(messages.catalog.products.empty);
    await user.type(screen.getByLabelText(messages.catalog.code), "espresso");
    await user.type(screen.getByLabelText(messages.catalog.name), "Espresso");
    await user.selectOptions(
      screen.getByLabelText(messages.catalog.products.productType),
      "coffee",
    );
    await user.click(
      screen.getByRole("button", { name: messages.catalog.create }),
    );

    expect(await screen.findByText("espresso")).toBeInTheDocument();
  });
});
